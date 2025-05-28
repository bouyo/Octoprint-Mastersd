/*
 * View model for OctoPrint-Mastersd
 *
 * Author: You
 * License: AGPLv3
 */
$(function() {
    function MastersdViewModel(parameters) {
        var self = this;

        self.color_active = '#8BC34A';
        self.color_passive = '#CFD8DC';
        self.color_active_txt = '#7CB342';
        self.color_passive_txt = '#90A4AE';

        self.printer = parameters[0];
        self.connection = parameters[1];

        self.delete_file_path = '';
        log.info("Master SD frontend");
        
        // assign the injected parameters, e.g.:
        // self.loginStateViewModel = parameters[0];
        // self.settingsViewModel = parameters[1];

        // TODO: Implement your plugin's view model here.
        
        // Is masterSD connected?
        self.connected = ko.observable(false);

        // Is masterSD busy?
        self.isBusy = ko.observable(false);

        // Is switching?
        self.isSwitching = ko.observable(false);

        // Is SD card present?
        self.sd_present = ko.observable(null);

        // Is masterSD controling the SD card {true: masterSD, false: 3D printer, null: no data}
        self.sd_control = ko.observable(null);

        self.currentState = ko.observable("State not detected");

        self.selectedPort = ko.observable(0);

        // Upload to SD card button disabled
        self.uploadDisabled = ko.observable(true);

        self.activeFolder = ko.observable('/sdcard');
        self.visibleFiles = ko.observableArray([]);
        self.visibleFolders = ko.observableArray([]);

        self.sdFiles = ko.observable(null);

        self.dialogTitle = ko.observable('');
        self.dialogContent = ko.observable('');

        self.autoRun = ko.observable(false);

        self.uploadProgress = null;
        self.uploadProgressBar = null;

        self.uploadProgressText = ko.observable(null);
        self.uploadProgressPercentage = ko.observable(null);


        self.currentPath = ko.pureComputed(function() {
            var activeFolder = self.activeFolder();
            var folders_all = activeFolder.split('/');
            var folders = folders_all.slice(2);
            var out = [];
            var path = "/sdcard";

            log.info(folders);

            if (folders.length > 0){
                folders.forEach((folder) => {
                    path += '/' + folder;
                    out.push({
                        name: folder,
                        path: path
                    });
                });
            }

            log.info(out);
            
            return out;
        });

        self.folderClick = function(folder){
            if (folder){
                var folder_path = folder.path;
                if (folder_path){
                    if (folder_path != self.activeFolder()){
                        log.info("Folder click");
                        self.activeFolder(folder_path);
                    }
                }
            }            
        }

        self.attemptFileDelete = function(folder, file){
            var path = folder + '/' + file.name;
            log.info("Attempting to delete " + path);
            $.ajax({
                url: "plugin/mastersd/delete",
                contentType: "application/json; charset=utf-8",
                type: "POST",
                dataType: "json",
                headers: {
                    "X-Api-Key": UI_API_KEY,
                },
                data: JSON.stringify({path: path}),
                error: (data) => {
                    log.info("Error!");
                    log.info(data);
                },
                success: (data) => {
                    log.info("File deleted!");
                    var sdFiles = Object.assign({},self.sdFiles());
                    sdFiles.free_size = (Number(sdFiles.free_size) + Number(file.size)).toString();
                    sdFiles.taken_size = (Number(sdFiles.taken_size) - Number(file.size)).toString();
                    var files = sdFiles.files.filter((f) => {
                        return JSON.stringify(file) !== JSON.stringify(f)
                    });
                    sdFiles.files = files.map(f => ({...f}));
                    log.info(sdFiles);
                    self.sdFiles(Object.assign({},sdFiles));
                }
            });
        }

        self.postFolderDelete = function(path){
            var sdFiles = Object.assign({},self.sdFiles());

            var rmFoldersIds = [];
            var rmFilesIds = [];
            var posChanges = [];
            var sizeDeleted = 0;

            var newFolders = sdFiles.folders.filter((folder, index) => {
                if (folder == path || folder.startsWith(path + '/')){
                    rmFoldersIds.push(index);
                    return false;
                }
                return true;
            });

            sdFiles.files.forEach((file, index) => {
                if (rmFoldersIds.includes(file.folder)){
                    rmFilesIds.push(index);
                    sizeDeleted += Number(file.size);
                    return
                }
                var posChange = 0;
                rmFoldersIds.forEach((id) => {
                    if (id < file.folder){
                        posChange += 1;
                    }
                });
                posChanges.push(posChange);
            });

            rmFilesIds.forEach((id) => {
                sdFiles.files.splice(id,1);
            });
            posChanges.forEach((n, id) => {
                sdFiles.files[id].folder -= n;
            });
            
            sdFiles.folders = newFolders;
        
            sdFiles.free_size = (Number(sdFiles.free_size) + sizeDeleted).toString();
            sdFiles.taken_size = (Number(sdFiles.taken_size) - sizeDeleted).toString();
            
            self.sdFiles(Object.assign({},sdFiles));
        }

        self.attemptFolderDelete = function(folder){
            var path = folder.path;
            log.info("Attempting to delete " + path);
            $.ajax({
                url: "plugin/mastersd/rmdir",
                contentType: "application/json; charset=utf-8",
                type: "POST",
                dataType: "json",
                headers: {
                    "X-Api-Key": UI_API_KEY,
                },
                data: JSON.stringify({path: path}),
                error: (data) => {
                    log.info("Error!");
                    log.info(data);
                },
                success: (data) => {
                    log.info("Folder deleted!");
                    self.postFolderDelete(path);                    
                }
            });
        }

        self.deleteFolder = function(folder){
            self.dialogTitle("Delete folder");
            self.dialogContent("Are you sure you want to delete " + folder.name + " and all of it's content?")
            self.showDialog("#sidebar_simpleDialog", function(dialog){
                var sdFiles = Object.assign({},self.sdFiles());   
                self.attemptFolderDelete(folder);
                dialog.modal('hide');
            });                
        }

        self.deleteFile = function(file){
            self.dialogTitle("Delete file");
            self.dialogContent("Are you sure you want to delete " + file.name + "?")
            self.showDialog("#sidebar_simpleDialog", function(dialog){             
                var sdFiles = Object.assign({},self.sdFiles());   
                self.attemptFileDelete(sdFiles.folders[file.folder], file);
                dialog.modal('hide');
            });                
        }

        self.browseFile = function(){
            var fileinput = document.getElementById("browse");
            fileinput.value = null;
            fileinput.click();
        }

        self.fileSelected = function(data, e){
            self.uploadFiles(e.target.files);
        }

        self.folderContent = ko.computed(function() {
            var activeFolder = self.activeFolder();
            if (self.sdFiles()){
                var sdFiles = Object.assign({},self.sdFiles());
                var files = [];
                var folders = [];
                var folder_id = sdFiles.folders.indexOf(activeFolder);
                if(folder_id >= 0){
                    files = sdFiles.files.filter((file) => file.folder == folder_id);
                    sdFiles.folders.forEach((folder_path, index) => {
                        var path_list = folder_path.split('/');
                        var folder_name = path_list.pop();
                        var parent_path = path_list.join('/');
                        if (parent_path == activeFolder){
                            folders.push({
                                id: index,
                                name: folder_name,
                                path: folder_path
                            });
                        }
                    });
                    self.visibleFiles(files);
                    self.visibleFolders(folders);
                    return []
                }else{
                    log.info("Could not find active folder");
                    return []
                }
            }else{
                log.info("No sd card data");
                return []
            }
            
        });

        self.masterStatus = ko.pureComputed(function() {
            if (!self.connected()){
                return 'Offline';
            } else if (self.isBusy()){
                return 'Busy';
            }
            return 'Online';
        });

        self.rpiColor = ko.pureComputed(function() {
            if (self.sd_control()){
                return self.color_active;
            } else {
                return self.color_passive;
            }
        });

        self.printerColor = ko.pureComputed(function() {
            if (self.sd_control()){
                return self.color_passive;
            }
            if (self.sd_control() === null){
                return self.color_passive;
            }
            return self.color_active;
        });

        self.buttonState = ko.computed(function (){
            return !(
                self.printer.isReady() &&
                !self.printer.isBusy()
            );
        });

        self.activeMaster = ko.pureComputed(function() {
            var name;
            
            if (self.sd_control()){
                name = "connected to MasterSD";
            }else if (self.sd_control() === null){
                name = "connection unknown";
            }else{
                name = "connected to the 3D Printer";
            }
            log.info(name);
            return name;
        });

        self.switchSdText = ko.pureComputed(function() {
            if (self.sd_control()){
                return "Return Control";
            }else{
                return "Take Control";
            }
        });

        self.switchSdDisabled = ko.pureComputed(function() {
            if (self.sd_control() === null || !self.connected()){
                return true;
            } else {
                if (!self.sd_control() && (self.printer.isBusy() || self.printer.isLoading())){
                    // can't take control
                    return true;
                }
                return false;
            }
        });

        self.getSizeUnit = function(space){
            var unit = '';
            var count = 0;
            if (space < 0){
                return '-';
            }
            while(space/1000 >= 1 && count < 2){
                count += 1;
                space = space / 1000;
            }
            switch (count){
                case 1:
                    unit = 'MB';
                    break;
                case 2:
                    unit = 'GB';
                    break;
                default:
                    unit = 'KB';
            }
            return space.toFixed(2) + unit
        }

        self.freeSpace = ko.pureComputed(function() {
            if (self.sdFiles()){
                var sdFiles = Object.assign({}, self.sdFiles());
                return self.getSizeUnit(Number(sdFiles.free_size));
            }else{
                return '-'
            }            
        });

        self.allSpace = ko.pureComputed(function() {
            if (self.sdFiles()){
                var sdFiles = Object.assign({}, self.sdFiles());
                return self.getSizeUnit(Number(sdFiles.free_size) + Number(sdFiles.taken_size));
            }else{
                return '-'
            }
        });

        self.sleep = function(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        self.getSdInfo = function(){
            log.info("Attempting to get SD data")
            if (self.connected() && self.sd_control()){
                self.isBusy(true);
                self.isSwitching(true);
                $.ajax({
                    url: "plugin/mastersd/get_info",
                    type: "GET",
                    dataType: "json",
                    error: (data) => {
                        log.info("Get info failed!");
                        log.info(data);
                    },
                    success: (data) => {
                        log.info("Get info success!");
                        log.info(data);
                        self.sdFiles(Object.assign({},data));
                        self.activeFolder('/sdcard');
                    },
                    complete: (data) => {
                        self.isBusy(false);
                        self.isSwitching(false);
                    }
                });
            }
        }

        self.switchSd = function(){
            log.info("Attempting to switch the SD master")
            if (self.connected()){
                self.isSwitching(true);
                $.ajax({
                    url: "plugin/mastersd/switch_control",
                    type: "GET",
                    dataType: "json",
                    error: self.failedSwitch,
                    success: self.updateSwitch
                });
            }
        }

        self.failedSwitch = function(data){
            log.info("Switch failed");
            log.info(data);
            self.isSwitching(false);
        }

        self.updateSwitch = function(data){
            log.info("Switch success!");
            log.info(data);
            self.sd_control(data);
            self.isSwitching(false);
            if (data){
                self.sleep(100).then(() => self.getSdInfo());
            } else {
                self.sdFiles(null);
                self.activeFolder('/sdcard');
            }
        }

        self.setDisconnected = function(){
            self.connected(false);
            self.sd_present(null);
            self.sd_control(null);
            self.sdFiles(null);
            self.activeFolder('/sdcard');
        }

        self.attemptMakeDir = function(dirName, activeFolder){
            var path = activeFolder + '/' + dirName;
            log.info("Attempting to create folder: " + path);
            
            $.ajax({
                url: "plugin/mastersd/mkdir",
                contentType: "application/json; charset=utf-8",
                type: "POST",
                dataType: "json",
                headers: {
                    "X-Api-Key": UI_API_KEY,
                },
                data: JSON.stringify({path: path}),
                error: (data) => {
                    log.info("Error!");
                    log.info(data);
                },
                success: (data) => {
                    log.info("Folder created!");
                    var sdFiles = Object.assign({},self.sdFiles());
                    sdFiles.folders.push(path);
                    log.info(sdFiles);
                    self.sdFiles(Object.assign({},sdFiles));
                }
            });            
        }

        self.addDirClick = function(){
            self.dialogTitle("Create new directory");
            self.dialogContent("Name of the new directory:")
            self.showDialog("#sidebar_newFolder", function(dialog){
                var activeFolder = self.activeFolder();
                var dirNameInput = document.getElementById("new-folder-name");
                var dirName = dirNameInput.value;
                log.info("Folder name: " + dirName);
                
                //Check if folder name is missing
                if (dirName.length < 1){
                    return
                }

                // Check if folder name is taken
                var visibleFolders = self.visibleFolders();
                var folder_id = visibleFolders.findIndex((folder) => {
                    return (folder.name == dirName)
                })
                if (folder_id > -1){
                    return
                }
                
                //var sdFiles = Object.assign({},self.sdFiles());   
                self.attemptMakeDir(dirName, activeFolder);
                dialog.modal('hide');
            });    
        }
        
        self.uploadFiles = function(files){
            log.info(files);

            if (files){
                if (files.length > 0){
                    var data = new FormData();
                    var files_size = 0;
                    data.append('file', files[0]);
                    files_size += files[0].size
                    
                    var visibleFiles = self.visibleFiles();
                    log.info(files[0]);
                    log.info(visibleFiles);
                    log.info("Total file size: " + files_size);
                    if (files_size > 250000000){
                        log.info("Max upload limited to 250MB");
                    } else {
                        let file_id = visibleFiles.findIndex((visibleFile) => {
                            if (visibleFile.name == files[0].name){
                                return true
                            }
                                return false
                        });
                        log.info("File ID: " + file_id);
                        if (file_id > -1){
                            self.dialogTitle("File already exists");
                            self.dialogContent("Cannot write two files with the same name");
                            self.showDialog("#sidebar_simpleWarning", null); 
                        } else {
                            $.ajax({
                                url: "/api/files/local",
                                type: 'POST',
                                processData: false,
                                contentType: false,
                                cache: false,
                                enctype: 'multipart/form-data',
                                contentLength: files_size,
                                data: data,
                                headers: {
                                    "X-Api-Key": UI_API_KEY,
                                },
                                error: self.uploadFailed,
                                success: self.uploadSuccess
                            });                            
                        }                        
                    }                    
                }                
            }
        }

        self.uploadFailed = function(data){
            log.info("Upload failed!");
            log.info(data);

            self.uploadProgress.removeClass("progress-striped").removeClass("active");
            self.uploadProgressBar.css("width", "0");
            self.uploadProgressText("");
            self.uploadProgressPercentage(0);
        }

        self.writeSuccess = function(data){
            log.info('Write success!');
            log.info(data);
            if (data.autorun){
                log.info("Disconnected!");
                self.sdFiles(null);
                self.activeFolder('/sdcard');
                self.isBusy(false);
                self.sd_control(false);
            }else{
                var sdFiles = Object.assign({},self.sdFiles());
                var file = {
                    folder: sdFiles.folders.indexOf(self.activeFolder()),
                    name: data.name,
                    size: data.size
                };            
                sdFiles.files.push(file);
                sdFiles.free_size = (Number(sdFiles.free_size) - Number(file.size)).toString();
                sdFiles.taken_size = (Number(sdFiles.taken_size) + Number(file.size)).toString();
                self.sdFiles(Object.assign({},sdFiles));
                log.info(sdFiles);
            } 
            
            self.uploadProgress.removeClass("progress-striped").removeClass("active");
            self.uploadProgressBar.css("width", "0");
            self.uploadProgressText("");
            self.uploadProgressPercentage(0);
        }

        self._setProgressBar = function (percentage, text, active) {
            self.uploadProgressBar.css("width", percentage + "%");
            self.uploadProgressText(text);
            self.uploadProgressPercentage(percentage);

            if (active) {
                self.uploadProgress.addClass("progress-striped active");
            } else {
                self.uploadProgress.removeClass("progress-striped active");
            }
        }

        self.uploadSuccess = function(data){
            log.info("Upload successful!");
            log.info(data);

            if (data.done){
                // Progress bar
                self.uploadProgress.addClass("progress-striped").addClass("active");
                self.uploadProgressBar.css("width", "100%");
                self.uploadProgressPercentage(100);
                self.uploadProgressText(gettext("Uploading ..."));

                var name = data.files.local.path;
                if (name){
                    $.ajax({
                        url: "plugin/mastersd/write_sd",
                        contentType: "application/json; charset=utf-8",
                        type: "POST",
                        dataType: "json",
                        headers: {
                            "X-Api-Key": UI_API_KEY,
                        },
                        data: JSON.stringify({name: name, path: self.activeFolder(), run: self.autoRun()}),
                        error: self.uploadFailed,
                        success: self.writeSuccess
                    });
                }
            }            
        }
     

        self.portOptions = ko.computed(function() {
            const port_list = self.connection.portOptions().slice();

            // Remove port if it's taken by the printer
            if (self.connection.isOperational()){
                if (self.connection.selectedPort()){
                    const i = port_list.indexOf(self.connection.selectedPort());
                    if (i > -1) {
                        port_list.splice(i, 1);
                    }
                }
            }
            
            const regex = new RegExp('/dev/ttyACM*');
            const sd_ports = port_list.filter((port) => regex.test(port));
            sd_ports.unshift("AUTO");
            
            //self.connectBtnLocked(sd_ports.length == 1)
            if (sd_ports.length == 1){
                self.setDisconnected();
            }            
            
            return sd_ports;
        });

       
        self.connectMasterSD = function(){
            self.isBusy(true);
            if (!self.connected()){
                let ports = [];
                let selectedPort = self.selectedPort();
                let allPorts = self.portOptions();
                log.info("Selected port: " + selectedPort);
                log.info("All ports: " + allPorts);
                if (selectedPort === "AUTO"){
                    ports = allPorts.slice(1);
                } else {
                    ports.push(selectedPort);
                }
                if (ports.length > 0){
                    log.info("Connecting to masterSD!");
                    log.info("Testing ports: " + JSON.stringify(ports));
                    $.ajax({
                        url: "plugin/mastersd/connect",
                        contentType: "application/json; charset=utf-8",
                        type: "POST",
                        dataType: "json",
                        headers: {
                            "X-Api-Key": UI_API_KEY,
                        },
                        data: JSON.stringify({ports: ports}),
                        error: self.failedToComm,
                        success: self.updateConnected
                    });
                } else {
                    log.info("No available port found");
                }                
            } else {
                log.info("Trying to disconnect!");
                $.ajax({
                    url: "plugin/mastersd/disconnect",
                    type: "GET",
                    dataType: "json",
                    error: (data) => {
                        log.info("Disconnection failed!");
                        log.info(data);
                        self.isBusy(false);
                    },
                    success: (data) => {
                        log.info("Disconnected!");
                        log.info(data);
                        self.sdFiles(null);
                        self.activeFolder('/sdcard');
                        self.isBusy(false);
                        self.sd_control(null);
                        self.sd_present(null)
                        self.connected(false);
                    }
                });
            }            
        }

        self.failedToComm = function(data){
            log.info("Connection failed");
            log.info(data);
            self.sdFiles(null);
            self.activeFolder('/sdcard');
            self.sd_control(null);
            self.connected(false);
            self.sd_present(null)
            self.isBusy(false);
        }

        self.updateConnected = function(data){
            log.info("Connection success!");
            log.info(data);
            self.sd_control(data);
            self.connected(true);
            self.isBusy(false);
            if (data){
                self.sleep(100).then(() => self.getSdInfo());
            }
        }


        /* EXAMPLE FOR API CALLS

        self.refreshMasterSD = function(){
            log.info("Refreshing MasterSD ports!");
            $.ajax({
                url: "plugin/mastersd/ports",
                type: "GET",
                dataType: "json",
                headers: {
                    "X-Api-Key":UI_API_KEY,
                },
                success: self.updatePorts
            });
        }
        
        self.updatePorts = function(data){
            log.info("Received ports!")
            log.info(data);
            if (self.portOptions().length > 1){
                self.portOptions.remove(function (el) {
                    return el !== "AUTO";
                });
            }
            data.forEach((el) => self.portOptions.push(el));
        }
        */

        // Change the upload percantage
        self.onEventPluginMastersdUploadProgress = function(payload){

            var progress = parseInt(payload.percentage);
            var uploaded = progress >= 100;

            log.info("Received percentage " + payload.percentage);
            self._setProgressBar(
                progress,
                gettext(payload.percentage + " %"),
                uploaded
            );
        }

        self.onBeforeBinding = function() {
            log.info("Printer State Loaded:");
            log.info(self.printer);
        }

        self.onStartupComplete = function(){

            $(document).on('hidden.bs.modal', '#sidebar_newFolder', function() {
                log.info("Modal hidden");
                $('#new-folder-name').val('');
            });
            self.uploadProgress = $("#mastersd_upload_progress");
            self.uploadProgressBar = $(".bar", self.uploadProgress);
        }

        self.showDialog = function(dialogId, confirmFunction){
            // show dialog
            // sidebar_deleteFilesDialog
            var myDialog = $(dialogId);
            var confirmButton = null;
            if (dialogId != '#sidebar_simpleWarning'){
                confirmButton = $("button.btn-confirm", myDialog);
                confirmButton.unbind("click");
                confirmButton.bind("click", function() {
                    confirmFunction(myDialog);
                });
            }
            var cancelButton = $("button.btn-cancel", myDialog);
                        
            myDialog.modal({
                //minHeight: function() { return Math.max($.fn.modal.defaults.maxHeight() - 80, 250); }
            }).css({
                width: 'auto',
                'margin-left': function() { return -($(this).width() /2); }
            });
        }
    }

    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: MastersdViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: [ "printerStateViewModel", "connectionViewModel"/* "loginStateViewModel", "settingsViewModel" */ ],
        // Elements to bind to, e.g. #settings_plugin_mastersd, #tab_plugin_mastersd, ...
        elements: [ "#tab_plugin_mastersd"/* ... */ ]
    });
});
