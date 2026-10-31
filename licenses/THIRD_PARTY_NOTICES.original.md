# Audio decoder notices

Audio import uses miniaudio 1.71 (Python bindings, MIT license). License texts
are included under licenses/miniaudio-*. The embedded miniaudio library and dr_libs
components provide their own permissive license alternatives as recorded there.
Project sources: https://github.com/irmen/pyminiaudio
Underlying library: https://github.com/mackron/miniaudio

MP3 and WAV are decoded locally to short PCM WAV files; playback uses Qt's
QSoundEffect. No system MP3 codec installation or external ffmpeg executable is used.
