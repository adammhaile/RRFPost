# ToolChanger Post-Processor

This project was created with the intent to provide useful ToolChanger gcode post-processor functions for use in PrusaSlicer or any other slicer that supports post scripts.

As of February 2021, the only contained functionality is that of automatic tool pre-heat. More is planned for the future.

# Disclaimer

I do my absolute best to fully test everything, but this is still something that is modifying your gcode, and everyone's setup is different. By using this post-processor you agree to take full liability for the your printer safety and any harm or damage that may be caused by using this code. 

## Tool Preheat

Currently PrusaSlicer (or most slicers for that matter) do not support automatic tool preheat. Functionally, this means that if you use a standby temperature you will have to wait for the tool to come back up to temperature before printing will continue. TCPost's preheat functionality solves that issue by injecting changes to the standby temperature so that it's ready to go the moment a tool is picked up.

Before continuing, please note this script was written specifically with the E3D ToolChanger in mind and therefore also the Duet controller with RepRapFirmware. It could likely work with other Duet-based multi-tool machines but it has not been tested on anything else. It also was designed for use specifically with PrusaSlicer 2.3 or newer.

### Setup

- In PrusaSlicer 2.3 you MUST configure your printer profile to use the `RepRapFirmware` flavor and NOT the older `RepRap/Sprinter` option. This is because TCPost depends on `G10` being used for temperature changes. Earlier versions of PrusaSlicer will not work because they do not support the `G10` command.
- PrusaSlicer does not currently support standby temperatures, so you must add them to your start-up gcode. Add a `G10 P0 R170` line for each tool. The `P` value is the tool number and `R` is the standby temperature. You must provide this for each tool. TCPost will automatically discover the active and standby temperatures to use by parsing these values. It will even handle temperature changes throughout the gcode file as long as they use `G10`.
- Under `Print Settings` > `Output Options` > `Post-processing Scripts` add the line: `python /path/to/tcpost.py --preheat SECONDS` where `SECONDS` is how early you want to heat up the next tool and with whatever path represents where you places the `tcpost.py` script.
- The seconds parameter is really a minimum value. The script does it's best to simulate the printer movement and predict the correct time to place the pre-heat command. However, it cannot know your machine's specific accelerations profile (yet) so the preheat may happen a little earlier than the specified time. So you may want to tune that value to achieve the best results.
- You may need to provide the full path to your `python` binary depending on your system and if python is correctly setup in your system path.
- This will need to be done on EACH print profile in PrusaSlicer you want to use this post script on.

That's it. With that setup, the script will automatically run when exporting or sending the file to your printer remotely. You will see the standby temperature of the next tool change to the active tempture at least the configured amount of seconds before the next tool change.

When walking through the gcode, if the configured time exceeds the amount of time between two tool changes, it will simply insert the pre-heat directly after the last tool change.

