import serial, glob
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
    
    def is_control(self, s):
        self._logger.info("Checking control...")
        s.write(b'is_control\n')
        while(True):
            a = s.readline()
            self._logger.info("Received: %s", a.decode('ascii'))
            if (a == b'true\n'):
                return True                
            elif (a == b'false\n'):
                return False
            else:
                return None
            
    def take_control(self, s):
        self._logger.info("Taking control of the SD card!")
        s.write(b'take_control\n')  # Send data
        while(True):
            a = s.readline()
            if(a == b'done\n'):
                self._logger.info("Success!")
                return True
            else:
                self._logger.info("Failed")
                return False

    def return_control(self, s):
        self._logger.info("Returning control of the SD card!")
        s.write(b'return_control\n')  # Send data
        while(True):
            a = s.readline()
            if(a == b'done\n'):
                self._logger.info("Success!")
                return True
            else:
                self._logger.info("Failed")
                return False
            
    def write_file(self, s, path, name):
        self._logger.info("Writing to the SD card!")
        
        # 1 -- create file
        s.write(b'write ' + name.encode('ascii'))
        code = 0
        while(True):
            a = s.readline()
            if(a == b'done\n'):
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
            while(True):
                if (counter == 0):
                    msg = f.read(self.ADD_MAX-4)
                    if msg:
                        msg = 'add ' + msg
                else:
                    msg = f.read(self.ADD_MAX)
                
                if not msg:
                    s.write(b'done\n')
                    res_c = 0
                    while(True):
                        res_c += 1
                        a = s.readline()
                        if(a == b'done\n'):
                            self._logger.info("Writting complete!")
                            break
                        elif(res_c > 2):
                            return False
                        else:
                            self._logger.info(a.decode('ascii'))
                    break

                s.write(msg.encode('ascii'))
                counter += 1
                res_c = 0
                while(True):
                    res_c += 1
                    a = s.readline()
                    if(a == b'done\n'):
                        break
                    elif(res_c > 2):
                        return False                    
            return True

            
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
    
    @octoprint.plugin.BlueprintPlugin.route("/write_sd", methods=["POST"])
    def mastersd_write(self):
        self._logger.info("Attempting to write to SD!")
        data = flask.request.json
        name = data.get('name')

        if (not name):
            return flask.Response(
                "Name is None",
                status=400
            )
        
        self._logger.info("Searching for file %s", name)
        path_on_disk = self._file_manager.path_on_disk(self.local, name)
        self._logger.info(f"Path: {path_on_disk}")

        res = self.write_file(self.ser, path_on_disk, name)
        if (res):
            self._logger.info("Writting successful!")
            return flask.jsonify(success=True)
        
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
                self._logger.info("Sending command to return control over serial")
                ret = self.return_control(self.ser)
            else:
                self._logger.info("Sending command to take control over serial")
                ret = self.take_control(self.ser)

            if (ret):
                self.control = not self.control
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
    
    

__plugin_name__ = "MasterSD"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = MasterSDPlugin()