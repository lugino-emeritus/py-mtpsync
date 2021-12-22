# MTP-Sync

Tool to synchronize data to a slow device, e.g. a smartphone which is connected over MTP.
A state file (`.mtp_sync_state.json`) is created in the destination folder containing the time stamps of the synchronized files.


#### Dependencies

Python3.6 or newer is necessary.

`ntlib.imp` from [here](https://github.com/lugino-emeritus/py-ntlib) is used to set a basic log config. It is not necessary, just remove the import statement and `ntimp.config_log` if you do not want to download ntlib.


## Usage

Start the script with `python mtp-sync.py [-h]` or `./mtp-sync.py [-h]` for more informations.
To find the path where your OS mounts mtp devices, search the internet.


#### Miscellaneous

I developed this script to send music to my smartphone. Since this is connected using MTP it does not support time stamps. Therefore `rsync` has some problems. I also tested other programs, but none of them satisfied me.

For the first synchronization (or if some data is already synchronized) you may want to call the script with options `--size-only --write-state`.
