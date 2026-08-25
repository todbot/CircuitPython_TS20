# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: Unlicense

# Simple test of the TS20 capacitive touch sensor library.
# Prints out which of the 20 touch pads are being touched.
# Open the serial REPL after running to see the output.

import time

import board

import ts20

i2c = board.I2C()  # uses board.SCL and board.SDA

# Sensitivity is 0 (most sensitive) to 15 (least sensitive)
touch = ts20.TS20(i2c, sensitivity=5)

# The address can be changed if the ADD pin is tied to VDD:
# touch = ts20.TS20(i2c, 0x7A, sensitivity=5)

# And any single pad can be re-tuned at any time:
# touch[0].sensitivity = 10

while True:
    # touched_pads is a tuple of 20 booleans, one per pad
    touched = [pad for pad, is_touched in enumerate(touch.touched_pads) if is_touched]
    if touched:
        print("touched:", touched)
    time.sleep(0.25)  # small delay to keep from spamming output messages
