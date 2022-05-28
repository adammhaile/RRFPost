# RepRapFirmware / Duet Post-Processor

This project was created with the intent to provide useful RRF/Duet gcode post-processor functions for use in PrusaSlicer or any other slicer that supports post scripts.

As of May 2022, the only contained functionality is that of automatic tool pre-heat and pause based on length/mass. More is planned for the future.

# Disclaimer

I do my absolute best to fully test everything, but this is still something that is modifying your gcode, and everyone's setup is different. By using this post-processor you agree to take full liability for the your printer safety and any harm or damage that may be caused by using this code. 

Also, before continuing, please note this tool was written specifically for RRF/Duet compatible gcode. It is unlikely it will work for anything else and has not been tested with anything else. It also was designed for use specifically with PrusaSlicer 2.3 or newer.

# Installation

You can simply run:

`pip install rrfpost`

This will install `rrfpost` as a system command as well as the shorter alias `rrp`.

If you would like to install/run from source, clone this repository locally and run:

`python setup.py develop` 

You can change `develop` for `install` if you prefer to not have it automatically update when the code changes.

## Tool Preheat

Currently PrusaSlicer (or most slicers for that matter) do not support automatic tool preheat. Functionally, this means that if you use a standby temperature you will have to wait for the tool to come back up to temperature before printing will continue. RRFPost's preheat functionality solves that issue by injecting changes to the standby temperature so that it's ready to go the moment a tool is picked up.

### Setup

- In PrusaSlicer 2.3+ you MUST configure your printer profile to use the `RepRapFirmware` flavor and NOT the older `RepRap/Sprinter` option. This is because RRFPost depends on `G10` being used for temperature changes. Earlier versions of PrusaSlicer will not work because they do not support the `G10` command.
- PrusaSlicer does not currently support standby temperatures, so you must add them to your start-up gcode. Add a `G10 P0 R170` line for each tool. The `P` value is the tool number and `R` is the standby temperature. You must provide this for each tool. RRFPost will automatically discover the active and standby temperatures to use by parsing these values. It will even handle temperature changes throughout the gcode file as long as they use `G10`.
- Under `Print Settings` > `Output Options` > `Post-processing Scripts` add the line: `rrfpost preheat --sec SECONDS` where `SECONDS` is how early you want to heat up the next tool.
- The seconds parameter is really a minimum value. The script does it's best to simulate the printer movement and predict the correct time to place the pre-heat command. However, it cannot know your machine's specific accelerations profile (yet) so the preheat may happen a little earlier than the specified time. So you may want to tune that value to achieve the best results.
- Depending on your system, you may have to specify the full binary path for the `rrfpost` command.
    - On Linux/Mac run `which rrfpost` and use the path specified there in PrusaSlicer
    - On Windows run `where rrfpost` and use the path specified there in PrusaSlicer
- This will need to be done on EACH print profile in PrusaSlicer you want to use this post script on.

That's it. With that setup, `rrfpost` will automatically run when exporting or sending the file to your printer remotely. You will see the standby temperature of the next tool change to the active tempture at least the configured amount of seconds before the next tool change.

When walking through the gcode, if the configured time exceeds the amount of time between two tool changes, it will simply insert the pre-heat directly after the last tool change.

**Note:** I have noticed that currently with PrusaSlicer 2.4 it will sometimes not upload directly to your printer if you have any post-scripts. If this happens, simply use export and save locally, instead of upload. Then upload the resulting file manually.

## Automatic Pause

While filament runout sensors are great, I've always treated them as more of a last line of defense as they certainly can fail to trigger when you want them to. Instead I always try to make sure that I have enough filament to complete a job. However, this isn't always possible, especially on large prints that use more than 1kg of filament. This is why I created the `pause` option in `rrfpost`.

With this option you can specify either a weight or filament length at which to insert a pause, allowing you to manually swap to a new spool without worrying about it running out.

Note: unlike the `preheat` option, this is not meant to be run automatically from your slicer, but instead run manually when you have a specific need for it. This is because the parameters used each time will likely be different.

### Usage

Run `rrfpost pause <OPTIONS> <GCODE_PATH>` where `GCODE_PATH` is your file and `OPTIONS` are one or more of below:

- `--tool <TOOL_NUM>`: The tool number you want to apply this pause to as it would be referenced in the gcode. Such as T0, T1, T2, etc. If not provided it will use either T0 or any single tool that is called out in the file.
- `--diameter <DIAMETER>`: Only used for mass mode. The filament diameter in millimeters. If using PrusaSlicer this should automatically be detected.
- `--density <DENSITY>`: Only used for mass mode. The filament density in g/cm^3. If using PrusaSlicer this should automatically be detected from your filament profile. So make so it's correct in PrusaSlicer or correct it here to get the best results.
- `--mass <MASS>`: The mass or masses in grams that you want to pause at. You can provide comma delimted values (i.e. `--mass 250,950`) if you want to pause at multiple successive amounts. This is useful if you will be going through more than 2 spools in a single print. Not that after each target is reached the counter is reset, so these values are **NOT** cummulative.
- `--length <LENGTH>`: The length in millimeters to pause at.  You can provide comma delimted values (i.e. `--mass 35000,200000`) if you want to pause at multiple successive amounts. This is useful if you will be going through more than 2 spools in a single print. Not that after each target is reached the counter is reset, so these values are **NOT** cummulative.
- `--pausecode <GCODE>`: The gcode to inject into the file when pausing. This defaults to [`M226`](https://docs.duet3d.com/User_manual/Reference/Gcodes#m226-synchronous-pause). If you want to do something complex that would be more than a single line, it is recommended to put that in a macro on your printer and then insert that single macro call line here.

Note that `--mass` and `--length` are mutually exclusive. Also, if you are running more than one tool in a print and want to provide automatic pauses you can do so by running the tool more than once, changing the value of the `--tool` parameter each time.

## Wipe Tower Retract Fix

As noted in [this issue report](https://github.com/prusa3d/PrusaSlicer/issues/5377), PrusaSlicer will insert a move to the top of the wipe tower with an unretract before tool change. This is a holdover from the MMU way of doing things and there is no way to remove it from within PrusaSlicer at this time.

This command is simple and requires no arguments. When used it will find any of these instances, remove the move to the tower, and relocate the unretract to being **after** the tool change (when the new tool is already selected). So at the end of each tool's section in the gcode you will get the following:

- Unretract
- Change to new tool
- Move back over the wipe tower
- Unretract
- Purge to wipe tower

### Usage

You will need to add a call to this as a post-processing script just as noted for the [Tool Preheat Setup](#setup) but add the following:

`rrfpost wtrf`

That's it - those unwanted move/unretracts over the wipe tower will be removed.