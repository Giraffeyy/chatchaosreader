import asyncio
import os
import random
import re
import tempfile
import threading
import pygame
import edge_tts
import websockets

# CHAT CONFIG

TWITCH_USERNAME = "name"

ONLY_READ_MESSAGES_TO_ME = False

IGNORED_USERS = {
    "nightbot",
    "streamelements",
    "streamlabs",
}

IGNORE_COMMANDS = True
MAX_MESSAGE_LENGTH = 250

# VOICES & RANDOMIZATION

VOICES = [
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-EricNeural",
    "en-US-MichelleNeural",
    "en-US-RogerNeural",
    "en-US-AnaNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-CA-ClaraNeural",
    "en-CA-LiamNeural",
]

MIN_RATE = -25
MAX_RATE = 40
MIN_PITCH = -8
MAX_PITCH = 8
MIN_VOLUME = -5
MAX_VOLUME = 8

# AUDIO & OVERLAPPING PLAYBACK

pygame.mixer.init()
pygame.mixer.set_num_channels(64)


def clean_message(message: str) -> str:
    message = re.sub(r"https?://\S+", "link", message, flags=re.IGNORECASE)
    message = re.sub(r"\s+", " ", message)
    return message[:MAX_MESSAGE_LENGTH].strip()


def add_random_emphasis(message: str) -> str:
    words = message.split()
    if len(words) < 3:
        return message

    if random.random() < 0.22:
        words.insert(random.randint(1, len(words) - 1), "...")
    if random.random() < 0.35:
        words[random.randint(1, len(words) - 2)] += ","
    if random.random() < 0.12:
        idx = random.randrange(len(words))
        word = re.sub(r"[^A-Za-z0-9']", "", words[idx])
        if 2 <= len(word) <= 10:
            words[idx] = word.upper()

    return " ".join(words)


def _play_sound_thread(filename: str) -> None:
    """Plays sound on an open mixer channel in a separate thread."""
    try:
        sound = pygame.mixer.Sound(filename)
        channel = sound.play()
        if channel:
            while channel.get_busy():
                pygame.time.wait(30)
    except Exception as err:
        print(f"Audio Playback Error: {err}")
    finally:
        try:
            os.remove(filename)
        except OSError:
            pass


async def speak_message_immediately(message: str) -> None:
    """Generates audio and triggers playback immediately in parallel."""
    try:
        voice = random.choice(VOICES)
        rate = random.randint(MIN_RATE, MAX_RATE)
        pitch = random.randint(MIN_PITCH, MAX_PITCH)
        volume = random.randint(MIN_VOLUME, MAX_VOLUME)
        formatted_message = add_random_emphasis(message)

        print(f"  TTS -> {voice} | rate={rate:+d}% | pitch={pitch:+d}Hz")

        communicate = edge_tts.Communicate(
            formatted_message,
            voice,
            rate=f"{rate:+d}%",
            pitch=f"{pitch:+d}Hz",
            volume=f"{volume:+d}%",
        )

        fd, filename = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        await communicate.save(filename)

        t = threading.Thread(target=_play_sound_thread, args=(filename,), daemon=True)
        t.start()

    except Exception as exc:
        print(f"TTS Generation Error: {exc}")


# ANONYMOUS TWITCH IRC WEBSOCKET

async def twitch_irc_reader() -> None:
    uri = "wss://irc-ws.chat.twitch.tv:443"
    channel = TWITCH_USERNAME.lower().strip()
    nick = f"justinfan{random.randint(10000, 99999)}"

    print()
    print("=" * 60)
    print(" ChatChaosReader")
    print("=" * 60)
    print(f" Target Channel : #{channel}")
    print(f" Connecting as  : {nick}")
    print("=" * 60)
    print()

    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send("PASS SCHMOOPIIE")
                await ws.send(f"NICK {nick}")
                await ws.send(f"JOIN #{channel}")

                print(f"CONNECTED & LISTENING to #{channel} chat!")
                print("Waiting for messages...\n")

                async for message in ws:
                    for raw in message.split("\r\n"):
                        if not raw:
                            continue

                        if raw.startswith("PING"):
                            await ws.send("PONG :tmi.twitch.tv")
                            continue

                        match = re.search(
                            r"(?:@[^ ]+ )?:(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)",
                            raw,
                        )
                        if match:
                            username = match.group(1)
                            text = match.group(2)

                            if username.lower() in IGNORED_USERS:
                                continue

                            if IGNORE_COMMANDS and text.startswith("!"):
                                continue

                            if ONLY_READ_MESSAGES_TO_ME and channel not in text.lower():
                                continue

                            cleaned_text = clean_message(text)
                            if not cleaned_text:
                                continue

                            print(f"[{username}] {cleaned_text}")

                            # Fire off an async task IMMEDIATELY for this message
                            asyncio.create_task(speak_message_immediately(cleaned_text))

        except (websockets.ConnectionClosed, Exception) as err:
            print(f"Connection lost ({err}). Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


# MAIN ENTRY POINT

async def main() -> None:
    try:
        await twitch_irc_reader()
    finally:
        pygame.mixer.quit()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down ChatChaosReader...")