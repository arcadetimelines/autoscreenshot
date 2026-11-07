Copy autoscreenshot.lua to your MAME folder

mame <romname> -skip_gameinfo -autoboot_script autoscreenshot.lua

It runs thesefive steps in order. The options are in a table at the top of the file:

Option								Default		Step
wait_before_coin_seconds			5			1. real seconds to wait before the coin
insert_coin							true		2. insert a coin or not
start_game							true		3. press the 1-player start button or not
wait_before_screenshot_seconds		10			4. real seconds to wait before the screenshot
exit_mame							true		5. exit MAME afterwards or not

If a step is turned off, the script skips it and carries on with the next one.

Real-time waits: they use os.time(), which counts wall-clock seconds, so the actual wait can be up to about a 
second short of what you set. Emulated time and the throttle speed don’t affect it.

Coin and start buttons: the script looks for the standard input names (“Coin 1”, “1 Player Start” and a few variants), 
then holds each button down for a few frames. If a game names its buttons differently, add the name to coin_names or start_names.
If a game ignores the presses, raise button_hold_frames.

Pause between coin and start: I added a short pause (frames_between_coin_and_start, in emulated frames) so the game 
registers the credit before start is pressed. Set it to 0 if you don’t want it.

Screenshot location: the image goes to MAME’s snapshot folder, snap/<romname>/ by default, so you can change it 
with -snapshot_directory.

MAME versions: the script uses emu.add_machine_frame_notifier when it exists and falls back to emu.register_frame_done on 
older versions.