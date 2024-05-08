import os
import serial
import octoprint.plugin
from octoprint.filemanager.destinations import FileDestinations
import flask
import sarge


class MasterSDPlugin(octoprint.plugin.StartupPlugin,
                     octoprint.plugin.TemplatePlugin,
                     octoprint.plugin.AssetPlugin,
                     octoprint.plugin.BlueprintPlugin):

    ser = None
    control = False
    local = FileDestinations.LOCAL
    ADD_MAX = 64

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

    def on_after_startup(self):
        self._logger.info("Master SD backend")
        self.ser = None
        self.control = False

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
        for port in ports:
            self._logger.info("Attempting to connect to port: %s", port)
            try:
                ser = serial.Serial(port, rate)
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
            file_info = os.stat(path_on_disk)
            file_size_bytes = file_info.st_size
            size = round(file_size_bytes / 1024)
            self._file_manager.remove_file(self.local, path_on_disk)
            self._logger.info("Writting successful!")
            return flask.jsonify({'name': name, 'size': size})

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
                command = "M21"  # Init SD
            else:
                self._logger.info(
                    "Sending command to take control over serial")
                ret = self.take_control(self.ser)
                command = "M22"  # Release SD

            if (ret):
                self.control = not self.control
                self._printer.commands(command)
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


__plugin_name__ = "MasterSD"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = MasterSDPlugin()
