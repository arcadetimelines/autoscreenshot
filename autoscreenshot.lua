-- autoscreenshot.lua
-- MAME Lua script: wait -> insert coin -> start game -> wait -> screenshot -> exit
--
-- Usage:
--   mame <romname> -skip_gameinfo -autoboot_script autoscreenshot.lua
--
-- Set skip_warnings to 1 in your ui.ini
--
-- Screenshots are saved by MAME in its snapshot directory (default: snap/<romname>/0000.png).
-- Change that location with MAME's "-snapshot_directory" option.

------------------------------------------------------------------------
-- OPTIONS (edit these)
------------------------------------------------------------------------
local options = {
    -- 1. Real-time seconds to wait before inserting a coin
    wait_before_coin_seconds = 15,

    -- 2. Insert a coin or not
    insert_coin = true,

    -- 3. Press the 1-player start button or not
    start_game = true,

    -- 4. Real-time seconds to wait before taking the screenshot
    --    (counted from the moment the previous step finished)
    wait_before_screenshot_seconds = 8,

    -- 5. Exit MAME after the screenshot or not
    exit_mame = true,

    -- Advanced: how many emulated frames a button is held down.
    -- Increase this if a game does not register the coin/start press.
    button_hold_frames = 10,

    -- Advanced: emulated frames to wait between the coin and the start press,
    -- so the game has time to register the credit.
    frames_between_coin_and_start = 30,

    -- Advanced: field names to look for (first match wins).
    -- Some games rename their buttons; add alternatives here.
    coin_names  = { "Coin 1", "Coin A", "Coin" },
    start_names = { "1 Player Start", "Start 1", "P1 Start", "1P Start" },
}

------------------------------------------------------------------------
-- Helpers
------------------------------------------------------------------------
local function log(msg)
    print("[autoscreenshot] " .. msg)
end

-- Print every I/O field of the machine (useful to find the right names)
local function dump_fields()
    log("---- I/O fields ----")
    for ptag, port in pairs(manager.machine.ioport.ports) do
        for fname, field in pairs(port.fields) do
            log(string.format("port=%s  field=%q  type=%s  player=%s",
                tostring(ptag), tostring(field.name), tostring(field.type), tostring(field.player)))
        end
    end
    log("--------------------")
end

-- Find an I/O field: first by its input type token (e.g. "COIN1", "START1"),
-- which does not depend on the game's button names; then by name as a fallback.
local function find_field(token, names)
    local ioport = manager.machine.ioport

    -- 1) by input type
    local ok, itype, iplayer = pcall(function() return ioport:token_to_input_type(token) end)
    if ok and itype then
        for _, port in pairs(ioport.ports) do
            for _, field in pairs(port.fields) do
                if field.type == itype and (iplayer == nil or field.player == iplayer) then
                    return field
                end
            end
        end
    end

    -- 2) by name
    for _, wanted in ipairs(names) do
        for _, port in pairs(ioport.ports) do
            for _, field in pairs(port.fields) do
                if field.name == wanted then
                    return field
                end
            end
        end
    end
    return nil
end

-- Real (wall-clock) time in seconds. os.time() has 1 second resolution,
-- which is fine for waits expressed in whole seconds.
local function now()
    return os.time()
end

------------------------------------------------------------------------
-- State machine
------------------------------------------------------------------------
local state = "wait_coin"
local state_started_real = nil   -- real time when the current wait began
local frames_left = 0            -- frame counter for button presses / gaps
local active_field = nil         -- button currently being held

local function start_wait(next_state)
    state = next_state
    state_started_real = now()
end

local function press(field, next_state)
    if not field then
        log("Button not found! Dumping all I/O fields so you can see the real names:")
        dump_fields()
        state = next_state
        return false
    end
    log("Pressing field: " .. tostring(field.name))
    field:set_value(1)
    active_field = field
    frames_left = options.button_hold_frames
    state = next_state
    return true
end

local function release()
    if active_field then
        active_field:set_value(0)
        active_field = nil
    end
end

local function after_coin()
    -- called once the coin step is finished
    if options.start_game then
        frames_left = options.frames_between_coin_and_start
        state = "gap_before_start"
    else
        start_wait("wait_screenshot")
    end
end

local function do_step()
    -- STEP 1: real-time wait before coin
    if state == "wait_coin" then
        if not state_started_real then
            state_started_real = now()
            log("Waiting " .. options.wait_before_coin_seconds .. "s before coin...")
        end
        if now() - state_started_real >= options.wait_before_coin_seconds then
            -- STEP 2: insert coin
            if options.insert_coin then
                log("Inserting coin.")
                press(find_field("COIN1", options.coin_names), "coin_held")
            else
                after_coin()
            end
        end

    elseif state == "coin_held" then
        frames_left = frames_left - 1
        if frames_left <= 0 then
            release()
            after_coin()
        end

    elseif state == "gap_before_start" then
        frames_left = frames_left - 1
        if frames_left <= 0 then
            -- STEP 3: start game
            log("Pressing start.")
            press(find_field("START1", options.start_names), "start_held")
        end

    elseif state == "start_held" then
        frames_left = frames_left - 1
        if frames_left <= 0 then
            release()
            start_wait("wait_screenshot")
            log("Waiting " .. options.wait_before_screenshot_seconds .. "s before screenshot...")
        end

    -- STEP 4: real-time wait before screenshot
    elseif state == "wait_screenshot" then
        if not state_started_real then
            start_wait("wait_screenshot")
        end
        if now() - state_started_real >= options.wait_before_screenshot_seconds then
            log("Taking screenshot.")
            manager.machine.video:snapshot()
            state = "after_screenshot"
            frames_left = 2 -- give MAME a couple of frames to write the file
        end

    -- STEP 5: exit MAME
    elseif state == "after_screenshot" then
        frames_left = frames_left - 1
        if frames_left <= 0 then
            state = "done"
            if options.exit_mame then
                log("Exiting MAME.")
                manager.machine:exit()
            end
        end
    end
end

------------------------------------------------------------------------
-- Hook into the emulation (runs once per emulated frame)
------------------------------------------------------------------------
if emu.add_machine_frame_notifier then
    -- newer MAME versions
    -- IMPORTANT: the returned subscription must be kept in a global variable.
    -- If it is garbage collected, MAME silently stops calling do_step, which
    -- is why only waits of 0 seconds used to work.
    autoscreenshot_subscription = emu.add_machine_frame_notifier(do_step)
else
    -- older MAME versions
    emu.register_frame_done(do_step)
end

log("Loaded. Steps: coin=" .. tostring(options.insert_coin) ..
    ", start=" .. tostring(options.start_game) ..
    ", exit=" .. tostring(options.exit_mame))
