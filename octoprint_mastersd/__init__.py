import os
import serial
import octoprint.plugin
import logging
from octoprint.filemanager.destinations import FileDestinations
from octoprint.util.comm import parse_firmware_line, serialList
from octoprint.util import RepeatedTimer
import flask
import sarge


class MasterSDPlugin(octoprint.plugin.StartupPlugin,
                     octoprint.plugin.TemplatePlugin,
                     octoprint.plugin.AssetPlugin,
                     octoprint.plugin.BlueprintPlugin,
                     octoprint.plugin.SettingsPlugin,
                     octoprint.plugin.EventHandlerPlugin):

    ser = None
    control = False
    local = FileDestinations.LOCAL
    ADD_MAX = 64

    last_ports = None
    autorefresh = None

    sd_data = None

    def list_find(self, l, item):
        if item in l:
            return l.index(item)
        else:
            return -1

    def get_sd_data(self, raw_data):
        folders = []
        files = []
        free_size = 0
        taken_size = 0
        lines = raw_data.splitlines()
        for i, line in enumerate(lines):
            if (i < len(lines) - 2):
                # files & folders part
                if ("/sdcard" in line and "s: " in lines[i+1]):
                    # is file
                    size = lines[i+1].split(" ")[-1]
                    path_split = line.rsplit("/", 1)
                    folder = path_split[0]
                    name = path_split[1]
                    folder_id = self.list_find(folders, folder)
                    if (folder_id == -1):
                        folder_id = len(folders)
                        folders.append(folder)
                    file_obj = {
                        "name": name,
                        "size": size,
                        "folder": folder_id
                    }
                    files.append(file_obj)
                else:
                    # is folder
                    if ("/sdcard" in line and line not in folders):
                        folders.append(line)
            else:
                # Size data
                data = line.split(" ")[-1]
                if ("Free size:" in line):
                    free_size = data
                elif ("Taken size:" in line):
                    taken_size = data

        out_obj = {
            "folders": folders,
            "files": files,
            "free_size": free_size,
            "taken_size": taken_size
        }
        return out_obj

    def is_control(self, s):
        self._logger.info("Checking control...")
        s.write(b'is_control\n')
        ret = None
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return ret
            else:
                self._logger.info("Received: %s", a.decode('ascii'))
                if (a == b'true\n'):
                    ret = True
                elif (a == b'false\n'):
                    ret = False
                else:
                    return None

    def take_control(self, s):
        self._logger.info("Taking control of the SD card!")
        s.write(b'take_control\n')  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return True
            else:
                self._logger.info("Failed")
                return False

    def return_control(self, s):
        self._logger.info("Returning control of the SD card!")
        s.write(b'return_control\n')  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return True
            else:
                self._logger.info("Failed")
                self._logger.info(a.decode('ascii'))
                return False

    def get_info(self, s):
        data = '/sdcard\n'
        s.write(b'get_info\n')  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return data
            else:
                data += a.decode('ascii')
                self._logger.info(a.decode('ascii'))

    def write_file(self, s, path, name):
        self._logger.info("Writing to the SD card!")

        # 1 -- create file
        s.write(b'write ' + name.encode('ascii'))
        code = 0
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("File created!")
                code = 100
                break
            else:
                self._logger.info("Did not create file!")
                code = 400
                return False

        self._logger.info("Trying to read from file...")
        with open(path, "r") as f:
            counter = 0
            while (True):
                if (counter == 0):
                    msg = f.read(self.ADD_MAX-4)
                    if msg:
                        msg = 'add ' + msg
                else:
                    msg = f.read(self.ADD_MAX)

                if not msg:
                    s.write(b'done\n')
                    res_c = 0
                    while (True):
                        res_c += 1
                        a = s.readline()
                        if (a == b'done\n'):
                            self._logger.info("Writting complete!")
                            break
                        elif (res_c > 2):
                            return False
                        else:
                            self._logger.info(a.decode('ascii'))
                    break

                s.write(msg.encode('ascii'))
                counter += 1
                res_c = 0
                while (True):
                    res_c += 1
                    a = s.readline()
                    if (a == b'done\n'):
                        break
                    elif (res_c > 2):
                        return False
            return True

    def delete_file(self, s, path):
        s.write(b'del ' + path.encode('ascii'))  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return True
            elif (a == b'failed\n'):
                self._logger.info("Wrong filename!")
                return False
            else:
                self._logger.info(a.decode('ascii'))

    def make_dir(self, s, name):
        self._logger.info("Creating a directory on the SD card")

        s.write(b'mkdir ' + name.encode('ascii'))  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return True
            elif (a == b'failed\n'):
                self._logger.info("Make directory failed!")
                return False
            else:
                self._logger.info(a.decode('ascii'))

    def remove_dir(self, s, path):
        self._logger.info(
            "Removing a directory and subdirectories on the SD card!")

        s.write(b'rmdir ' + path.encode('ascii'))  # Send data
        while (True):
            a = s.readline()
            if (a == b'done\n'):
                self._logger.info("Success!")
                return True
            elif (a == b'failed\n'):
                self._logger.info("Remove directory failed!")
                return False
            else:
                self._logger.info(a.decode('ascii'))

    def on_after_startup(self):
        self._logger.info("Master SD backend")
        self.ser = None
        self.control = False

        self.find_name = ''
        self.is_listing = False

    def on_event(self, event, payload):

        if event == octoprint.events.Events.CONNECTED:
            self._logger.info("Printer connected event triggered!")
            self.run_autorefresh()
        elif event == octoprint.events.Events.DISCONNECTED:
            self._logger.info("Printer disconnected event triggered!")

    def get_assets(self):
        return dict(
            js=["js/mastersd.js"],
            css=["css/mastersd.css"]
        )

    def is_blueprint_csrf_protected(self):
        return True

    @octoprint.plugin.BlueprintPlugin.route("/connect", methods=["POST"])
    def mastersd_connect(self):
        self._logger.info("Attempting to connect to masterSD!")
        data = flask.request.json
        ports = data.get('ports')

        rate = "4000000"
        timeout = 2.0  # 2 sec timeout
        for port in ports:
            self._logger.info("Attempting to connect to port: %s", port)
            try:
                ser = serial.Serial(port, rate, timeout=timeout)
                ret = self.is_control(ser)
                if (ret is not None):
                    self.control = ret
                    self.ser = ser
                    return flask.jsonify(self.control)
                else:
                    self.ser = None
                    self._logger.info("Return is None")
                    pass
            except:
                self.ser = None
                self._logger.info("Could not connect")
                pass

        return flask.Response(
            "Could not connect to masterSD",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/disconnect", methods=["GET"])
    def mastersd_disconnect(self):
        self._logger.info("Attempting to disconnect from masterSD!")

        if (self.ser):
            if (self.ser.is_open):
                if (self.control):
                    self._logger.info(
                        "Sending command to return control over serial")
                    ret = self.return_control(self.ser)
                    if (ret):
                        self._printer.init_sd_card()
                        self.control = not self.control
                    else:
                        self._logger.info("Failed to return control")
                self.ser.close()
                self.ser = None
                self._logger.info("Disconnected successfully!")
                return flask.jsonify(success=True)
            else:
                return flask.Response(
                    "Serial is not open!",
                    status=400
                )

        return flask.Response(
            "Could not disconnect",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/write_sd", methods=["POST"])
    def mastersd_write(self):
        self._logger.info("Attempting to write to SD!")
        data = flask.request.json
        name = data.get('name')
        path = data.get('path')
        autorun = data.get('run')
        path = path.replace("/sdcard", "", 1)
        if path != "":
            path = path + '/' + name
        else:
            path = name

        if (not name):
            return flask.Response(
                "Name is None",
                status=400
            )

        self._logger.info("Searching for file %s", name)
        path_on_disk = self._file_manager.path_on_disk(self.local, name)
        self._logger.info(f"Path: {path_on_disk}, Path on SD: {path}")

        res = self.write_file(self.ser, path_on_disk, path)
        if (res):
            self._logger.info("Writting successful!")

            file_info = os.stat(path_on_disk)
            file_size_bytes = file_info.st_size
            size = round(file_size_bytes / 1024)
            self._file_manager.remove_file(self.local, path_on_disk)

            self._logger.info(f"Autorun state: {autorun}")

            if (self._printer.is_ready() and autorun):
                self._logger.info("Autorun attempt!")
                # Switch SD control
                ret = self.return_control(self.ser)
                if (ret):
                    self.control = not self.control
                    # Init SD card
                    self._printer.init_sd_card()
                    # self._printer.commands("M21")
                    # Run print
                    self.find_name = name
                    self._logger.info(f"Finding short name...")

            return flask.jsonify({'name': name, 'size': size, 'autorun': autorun})

        return flask.Response(
            "Could not connect to masterSD",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/switch_control", methods=["GET"])
    def mastersd_switch_control(self):
        self._logger.info("Attempting to switch control of the SD!")

        if (self.ser is None):
            return flask.Response(
                "Serial communication closed",
                status=400
            )

        try:
            if (self.control):
                self._logger.info(
                    "Sending command to return control over serial")
                ret = self.return_control(self.ser)
                # command = "M21"  # Init SD
            else:
                self._logger.info(
                    "Sending command to take control over serial")
                ret = self.take_control(self.ser)
                # command = "M22"  # Release SD

            if (ret):
                if (self.control):
                    self._printer.init_sd_card()
                else:
                    self._printer.release_sd_card()
                self.control = not self.control
                # self._printer.commands(command)
                return flask.jsonify(self.control)
            else:
                self._logger.info("Failed to take control")
                pass
        except:
            self._logger.info("Could not connect")
            pass

        return flask.Response(
            "Could not switch the state of the SD",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/get_info", methods=["GET"])
    def mastersd_get_info(self):
        self._logger.info("Attempting to get info from the SD!")

        if (self.ser is None):
            return flask.Response(
                "Serial communication closed",
                status=400
            )
        if (not self.ser.is_open):
            return flask.Response(
                "Serial communication closed",
                status=400
            )
        if (not self.control):
            return flask.Response(
                "MasterSD not in control",
                status=400
            )

        self._logger.info("Sending command to get_info over serial")
        data = self.get_info(self.ser)
        self._logger.info(f"Received: {data}")

        if (data):
            self.sd_data = self.get_sd_data(data)
            self._logger.info("Sending SD data!")
            return flask.jsonify(self.sd_data)
        else:
            self._logger.info("No response!")
            pass

        return flask.Response(
            "Could not get info from the SD",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/delete", methods=["POST"])
    def mastersd_delete(self):
        self._logger.info("Attempting to delete from SD!")
        data = flask.request.json
        path = data.get('path')

        if (not path):
            return flask.Response(
                "Path is None",
                status=400
            )

        short_path = path.replace("/sdcard/", "", 1)
        self._logger.info(f"Deleting: {short_path}")
        res = self.delete_file(self.ser, short_path)
        if (res):
            self._logger.info("Delete successful!")
            return flask.jsonify(success=True)

        return flask.Response(
            "Could not delete file!",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/mkdir", methods=["POST"])
    def mastersd_mkdir(self):
        self._logger.info("Attempting to create directory on SD card!")
        data = flask.request.json
        path = data.get('path')

        if (not path):
            return flask.Response(
                "Path is None",
                status=400
            )

        short_path = path.replace("/sdcard/", "", 1)
        self._logger.info(f"Creating path: {short_path}")
        res = self.make_dir(self.ser, short_path)
        if (res):
            self._logger.info("Folder created successfully!")
            return flask.jsonify(success=True)

        return flask.Response(
            "Could not create folder!",
            status=400
        )

    @octoprint.plugin.BlueprintPlugin.route("/rmdir", methods=["POST"])
    def mastersd_rmdir(self):
        self._logger.info("Attempting to delete directory on SD card!")
        data = flask.request.json
        path = data.get('path')

        if (not path):
            return flask.Response(
                "Path is None",
                status=400
            )

        short_path = path.replace("/sdcard/", "", 1)
        self._logger.info(f"Deleting path: {short_path}")
        res = self.remove_dir(self.ser, short_path)
        if (res):
            self._logger.info("Folder deleted successfully!")
            return flask.jsonify(success=True)

        return flask.Response(
            "Could not delete folder!",
            status=400
        )

    # Custom port refreshing

    def refresh_serial_list(self):

        if not self._printer.is_operational():
            return

        new_ports = sorted(serialList())
        if new_ports != self.last_ports:
            self._logger.info(
                "Custom serial port list was updated, refreshing the port list in the frontend"
            )
            self._event_bus.fire(
                octoprint.events.Events.CONNECTIONS_AUTOREFRESHED,
                payload={"ports": new_ports},
            )
        self.last_ports = new_ports

    def autorefresh_active(self):
        # Autorefresh when printer is connected
        return self._printer.is_operational()

    def autorefresh_stopped(self):

        self._logger.info("Custom autorefresh of serial port list stopped")
        self.autorefresh = None

    def run_autorefresh(self):

        if self.autorefresh is not None:
            self.autorefresh.cancel()
            self.autorefresh = None

        self.autorefresh = RepeatedTimer(
            2.0,
            self.refresh_serial_list,
            condition=self.autorefresh_active,
            on_finish=self.autorefresh_stopped,
        )
        self.autorefresh.name = "Custom serial autorefresh worker"

        self._logger.info(
            "Starting custom autorefresh of serial port list")
        self.autorefresh.start()

    def get_short_filename(self, comm, line, *args, **kwargs):
        if self.find_name == '':
            return line

        if "Begin file list" in line and not self.is_listing:
            self.is_listing = True
            return line

        if "End file list" in line and self.is_listing:
            self.is_listing = False
            return line

        if self.find_name in line and self.is_listing:
            self._logger.info(f"Found line with short name: {line}")
            short_name = line.split(' ', 1)[0]
            self._logger.info(f"Short name: {short_name}")

            self._printer.select_file(
                path=short_name.lower(), sd=True, printAfterSelect=True)
            # Don't search anymore
            self.find_name = ''

        return line


__plugin_name__ = "MasterSD"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = MasterSDPlugin()


def __plugin_load__():
    plugin = MasterSDPlugin()

    global __plugin_implementation__
    __plugin_implementation__ = plugin

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.comm.protocol.gcode.received": plugin.get_short_filename
    }
