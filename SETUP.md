# Setup (one-time)

## 1. ElevenLabs (voice)
1. Go to https://elevenlabs.io, sign in, open Settings → API Keys.
2. Create an API key, copy it into `.env` as `ELEVENLABS_API_KEY=...`.
3. Pick a voice (or clone your own) under Voices, copy its Voice ID into `.env` as `ELEVENLABS_VOICE_ID=...`.

## 2. YouTube (upload)
1. Go to https://console.cloud.google.com, create a new project.
2. Under "APIs & Services" → "Library", search for "YouTube Data API v3" and enable it.
3. Under "APIs & Services" → "Credentials", create an "OAuth Client ID" of type "Desktop app".
4. Download the resulting JSON and save it as `client_secret.json` in this project's root folder.
5. The first time you run `python -m agent_video upload <video_dir>`, a browser window opens asking you to log in and approve access — do this once. A token is cached afterward so you won't need to repeat this step.

## 3. Install dependencies
```
pip install -r requirements.txt
```

## 4. Try it
```
python -m agent_video new "What If The Moon Disappeared"
# edit videos/ep01_.../script.md, add required images to its assets/ folder
python -m agent_video status videos/ep01_what-if-the-moon-disappeared
python -m agent_video build videos/ep01_what-if-the-moon-disappeared
python -m agent_video upload videos/ep01_what-if-the-moon-disappeared
```
