# Changelog

### 0.3.2 (2023-12-14)

* Removed key upload from room event handler
* Fixed output of `python -m gptbot -v` to display currently installed version
* Workaround for bug preventing bot from responding when files are uploaded to an encrypted room

#### Known Issues

* When using Pantalaimon: Bot is unable to download/use files uploaded to encrypted rooms

### 0.3.1 (2023-12-07)

* Fixed issue in newroom task causing it to be called over and over again