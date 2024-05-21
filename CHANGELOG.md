# Changelog

### 0.3.14 (2024-05-21)

- Fixed issue in handling of login credentials, added error handling for login failures

### 0.3.13 (2024-05-20)

- **Breaking Change**: The `ForceTools` configuration option behavior has changed. Instead of using a separate model for tools, the bot will now try to use the default chat model for tool requests, even if that model is not known to support tools.
- Added `ToolModel` to OpenAI configuration to allow specifying a separate model for tool requests
- Automatically resize context images to a default maximum of 2000x768 pixels before sending them to the AI model

### 0.3.12 (2024-05-17)

- Added `ForceVision` to OpenAI configuration to allow third-party models to be used for image recognition
- Added some missing properties to `OpenAI` class

### 0.3.11 (2024-05-17)

- Refactoring of AI provider handling in preparation for multiple AI providers: Introduced a `BaseAI` class that all AI providers must inherit from
- Added support for temperature, top_p, frequency_penalty, and presence_penalty in `AllowedUsers`
- Introduced ruff as a development dependency for linting and applied some linting fixes
- Fixed `gptbot` command line tool
- Changed default chat model to `gpt-4o`
- Changed default image generation model to `dall-e-3`
- Removed currently unused sections from `config.dist.ini`
- Changed provided Pantalaimon config file to not use a key ring by default
- Prevent bot from crashing when an unneeded dependency is missing

### 0.3.10 (2024-05-16)

- Add support for specifying room IDs in `AllowedUsers`
- Minor fixes

### 0.3.9 (2024-04-23)

- Add Docker support for running the bot in a container
- Add TrackingMore dependency to pyproject.toml
- Replace deprecated `pkg_resources` with `importlib.metadata`
- Allow password-based login on first login

### 0.3.7 / 0.3.8 (2024-04-15)

- Changes to URLs in pyproject.toml
- Migrated build pipeline to Forgejo Actions

### 0.3.6 (2024-04-11)

- Fix issue where message type detection would fail for some messages (cece8cfb24e6f2e98d80d233b688c3e2c0ff05ae)

### 0.3.5

- Only set room avatar if it is not already set (a9c23ee9c42d0a741a7eb485315e3e2d0a526725)

### 0.3.4 (2024-02-18)

- Optimize chat model and message handling (10b74187eb43bca516e2a469b69be1dbc9496408)
- Fix parameter passing in chat response calls (2d564afd979e7bc9eee8204450254c9f86b663b5)
- Refine message filtering in bot event processing (c47f947f80f79a443bbd622833662e3122b121ef)

### 0.3.3 (2024-01-26)

- Implement recursion check in response generation (e6bc23e564e51aa149432fc67ce381a9260ee5f5)
- Implement tool emulation for models without tool support (0acc1456f9e4efa09e799f6ce2ec9a31f439fe4a)
- Allow selection of chat model by room (87173ae284957f66594e66166508e4e3bd60c26b)

### 0.3.2 (2023-12-14)

- Removed key upload from room event handler
- Fixed output of `python -m gptbot -v` to display currently installed version
- Workaround for bug preventing bot from responding when files are uploaded to an encrypted room

#### Known Issues

- When using Pantalaimon: Bot is unable to download/use files uploaded to unencrypted rooms

### 0.3.1 (2023-12-07)

- Fixed issue in newroom task causing it to be called over and over again
