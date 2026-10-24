# Running WebMusicFolder on a NAS (Ugreen UGOS or similar, Docker app only)

1. Docker app > Image > Add / Local import, choose `webmusicfolder.tar`.
2. Docker app > Container > Create container from the image `webmusicfolder:latest`.
3. Port: map container port `8080` to a free host port (for example `8080`).
4. Storage (volumes), both are needed:
   - a NAS folder for your music  ->  `/music`
   - a NAS folder for app data (settings, queue, logs)  ->  `/data`
5. Environment (all optional):
   - `WMF_PASSWORD`: your login password. If unset, a random one is created on first start and
     printed in the container logs (Container > Logs); it is also in `/data/initial_password.txt`.
   - `PUID` / `PGID`: user and group to run as. Default is root (0) so the music folder is
     always writable; set your NAS user ids if you want files owned by that user.
   - `TZ`: for example `Europe/Lisbon`.
6. Restart policy: "Always" or "Unless stopped". Start it and open `http://<nas-ip>:<port>`.

The music folder can also be changed later in the app under Settings > General (use a path
inside a mounted volume, for example `/music/Downloads`).
