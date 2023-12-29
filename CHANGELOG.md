# Changelog

### 0.3.3 (WIP)

* Implement recursion check in response generation (e6bc23e564e51aa149432fc67ce381a9260ee5f5)
* Implement tool emulation for models without tool support (0acc1456f9e4efa09e799f6ce2ec9a31f439fe4a)

### 0.3.2 (2023-12-14)

* Removed key upload from room event handler
* Fixed output of `python -m gptbot -v` to display currently installed version
* Workaround for bug preventing bot from responding when files are uploaded to an encrypted room

#### Known Issues

* When using Pantalaimon: Bot is unable to download/use files uploaded to encrypted rooms

### 0.3.1 (2023-12-07)

* Fixed issue in newroom task causing it to be called over and over again