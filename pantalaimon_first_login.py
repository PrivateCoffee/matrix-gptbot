from nio import AsyncClient

from configparser import ConfigParser

async def main():
    config = ConfigParser()
    config.read("config.ini")

    user_id = input("User ID: ")
    password = input("Password: ")

    client = AsyncClient(config["Matrix"]["Homeserver"])
    client.user = user_id
    await client.login(password)

    print("Access token: " + client.access_token)

    await client.close()

if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())