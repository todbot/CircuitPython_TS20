# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT
"""
`ts20`
================================================================================

Driver for TouchSemi TS20 I2C capacitive touch chip

The TS20 is a 20-channel capacitive touch sensor with automatic sensitivity
calibration.  Pads are numbered 0-19 in this library; the datasheet calls them
channels CS1-CS20.  Sensitivity is 0-15, where 0 is the *most* sensitive and 15
the least (it is really a touch threshold).

Usage:

.. code-block:: python

    import board
    import ts20

    touch = ts20.TS20(board.I2C(), sensitivity=3)  # all pads
    touch[7].sensitivity = 8       # pad 7 only, less sensitive
    touch.sensitivity = 5          # back to 5 for every pad
    print(touch.touched_pads)      # tuple of 20 booleans
    print(touch[7].value)          # single pad


* Author(s): Tod Kurt

Implementation Notes
--------------------

**Hardware:**

* AD Semiconductor / TouchSemi TS20 20-channel capacitive touch sensor

* For an example board, see https://github.com/todbot/TS20_Test_Board/

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads
* Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

Some aspects of this library copy functions from
`Adafruit_CircuitPython_CAP1188 <https://github.com/adafruit/Adafruit_CircuitPython_CAP1188>`_
and `Adafruit_CircuitPython_MPR121 <https://github.com/adafruit/Adafruit_CircuitPython_MPR121>`_.
Configuration information from `yni2yni/TS20 <https://github.com/yni2yni/TS20>`_.
"""

import time

from adafruit_bus_device import i2c_device
from micropython import const

try:
    from typing import List, Optional, Sequence, Tuple, Union

    import busio
except ImportError:
    # typing hint modules not needed or not available in CircuitPython
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/todbot/CircuitPython_TS20.git"

_TS20_DEFAULT_ADDRESS = const(0x6A)  # ADD pin = GND (0x7A if ADD = VDD)

NUM_PADS = const(20)

_TS20_SEN_PWM1 = const(0x00)  # ch2,ch1  (through _SEN_PWM11 at 0x0A)
_TS20_GTRL1 = const(0x0B)
_TS20_GTRL2 = const(0x0C)
_TS20_CAL_CTRL = const(0x0D)

_TS20_PORT_CTRL1 = const(0x0E)  # through _PORT_CTRL6 at 0x13
_TS20_PORT_CTRL6 = const(0x13)

_TS20_CAL_HOLD1 = const(0x14)
_TS20_CAL_HOLD2 = const(0x15)
_TS20_CAL_HOLD3 = const(0x16)
_TS20_ERR_CTRL = const(0x17)

_TS20_OUTPUT1 = const(0x20)  # through _OUTPUT3 at 0x22

_TS20_SEN_RD_CTRL = const(0x28)
_TS20_SEN_RD = const(0x29)

# GTRL2 bit fields
_GTRL2_IMP_SEL = const(0x10)  # 1 = high impedance
_GTRL2_SRST = const(0x08)  # 1 = hold digital block in reset
_GTRL2_RB_SEL_NORMAL = const(0x02)  # internal clock speed, 10 = normal

# Hand-tuned register values that work well on the sketchingpad hardware.
# Both are opaque bit fields; see datasheet 8.2.4 and 8.2.7.
_DEFAULT_CAL_CTRL = const(0xAF)  # calibration speed
_DEFAULT_ERR_CTRL = const(0x0F)  # noise rejection: 0.7% level, 3 counts

DEFAULT_SENSITIVITY = const(15)

# Which pad's sensitivity lives in the (low, high) nibble of each
# Sensitivity/PWM register.  ch7 and ch20 have no partner channel.
# fmt: off
_SENS_NIBBLES = (
    (0, 1), (2, 3), (4, 5), (6, None), (7, 8), (9, 10),
    (11, 12), (13, 14), (15, 16), (17, 18), (19, None),
)
# fmt: on
# Value for the unused high nibble: reg 0x03's reserved bits want "1111"
# (datasheet 8.2.1), reg 0x0A's empty bits want zero (register map note 2)
_SENS_FILL = (0, 0, 0, 0xF0, 0, 0, 0, 0, 0, 0, 0x00)


class TS20_Pad:
    """A single touch pad. Get one with ``ts20[pad_num]``."""

    def __init__(self, ts20: "TS20", pad: int) -> None:
        self._ts20 = ts20
        self._pad = pad

    @property
    def value(self) -> bool:
        """True if this pad is being touched."""
        return self._ts20.is_touched(self._pad)

    @property
    def sensitivity(self) -> int:
        """Sensitivity of this pad, 0 (most sensitive) to 15 (least)."""
        return self._ts20.sensitivity[self._pad]

    @sensitivity.setter
    def sensitivity(self, value: int) -> None:
        self._ts20.set_sensitivity(value, self._pad)

    @property
    def sensitivity_percent(self) -> float:
        """Sensitivity setting of this pad as a capacitance-change percent."""
        return self._ts20.sensitivity_percent(self._pad)


class TS20:
    """Driver for the TS20 connected over I2C.

    :param i2c: the I2C bus the TS20 is on
    :param address: I2C address, 0x6A (ADD=GND) or 0x7A (ADD=VDD)

    All remaining options are keyword-only:

    :param sensitivity: 0 (most sensitive) to 15 (least), either a single
        value for every pad or a 20-element list of per-pad values
    :param fine_steps: sensitivity step size. False (default) gives
        normal steps of 0.2%, True gives fine steps of 0.1%
    :param fast_mode: True (default) always sensing at the fast rate,
        False alternates between fast and slow to save power
    :param response_time: how many sense periods a touch must persist
        before it is reported, 0-7
    :param first_touch_time: length of the fast-calibration window after
        reset, 0-3 (13, 25, 50, 100 * 16 periods)
    :param high_impedance: True for high sense impedance (more
        sensitive, noisier), False (default) for low
    :param cal_ctrl: raw Cal_CTRL calibration-speed register value
    :param err_ctrl: raw Err_CTRL noise-rejection register value
    :param reset_on_change: bracket runtime sensitivity writes in a soft
        reset so the chip latches them. Set False if your board picks up
        the new values without it; a soft reset restarts calibration and
        so blanks touches for a moment.
    """

    def __init__(  # noqa: PLR0913  a config-heavy driver, all keyword args
        self,
        i2c: busio.I2C,
        address: int = _TS20_DEFAULT_ADDRESS,
        *,
        sensitivity: Union[int, Sequence[int]] = DEFAULT_SENSITIVITY,
        fine_steps: bool = False,
        fast_mode: bool = True,
        response_time: int = 2,
        first_touch_time: int = 1,
        high_impedance: bool = False,
        cal_ctrl: int = _DEFAULT_CAL_CTRL,
        err_ctrl: int = _DEFAULT_ERR_CTRL,
        reset_on_change: bool = True,
    ) -> None:
        self._i2c = i2c_device.I2CDevice(i2c, address)
        self._buf = bytearray(2)
        self._sens = bytearray(NUM_PADS)  # shadow copy of pad sensitivities
        self._sens_buf = bytearray(len(_SENS_NIBBLES))
        self._pads: List[Optional[TS20_Pad]] = [None] * NUM_PADS
        self.reset_on_change = reset_on_change
        self.cal_ctrl = cal_ctrl
        self.err_ctrl = err_ctrl
        self.fine_steps = fine_steps
        # GTRL1: -, SSC, MS, FTC[1:0], RTC[2:0]  (datasheet 8.2.2)
        self._gtrl1 = (
            (0 if fine_steps else 1) << 6
            | (1 if fast_mode else 0) << 5
            | (first_touch_time & 0x03) << 3
            | (response_time & 0x07)
        )
        # GTRL2 run value: multi-output mode, reset released (datasheet 8.2.3)
        imp = _GTRL2_IMP_SEL if high_impedance else 0
        self._gtrl2 = imp | _GTRL2_RB_SEL_NORMAL
        self._store_sensitivity(sensitivity)
        self.reset()

    def __getitem__(self, pad: int) -> "TS20_Pad":
        if pad < 0 or pad >= NUM_PADS:
            raise IndexError("pad must be 0-19")
        if self._pads[pad] is None:
            self._pads[pad] = TS20_Pad(self, pad)
        return self._pads[pad]

    def _write_register(self, reg_addr: int, reg_val: int) -> None:
        """Write 8 bit value to register at address."""
        self._buf[0] = reg_addr
        self._buf[1] = reg_val
        with self._i2c as i2c:
            i2c.write(self._buf)

    def _read_block(self, start: int, length: int) -> bytearray:
        """Return byte array of values from start address to length."""
        result = bytearray(length)
        with self._i2c as i2c:
            i2c.write(bytes((start,)))
            i2c.readinto(result)
        return result

    def _write_block(self, start: int, data: bytes) -> None:
        """Write out data beginning at start address."""
        with self._i2c as i2c:
            i2c.write(bytes((start,)) + data)

    def write_config(self, config_info: Sequence[Tuple[int, int]]) -> None:
        """Write an arbitrary set of registers to the TS20.
        'config_info' is a list of (reg_addr, reg_val) tuples.
        Escape hatch for registers this driver does not expose.
        """
        for reg_addr, reg_val in config_info:
            self._write_register(reg_addr, reg_val)

    def reset(self) -> None:
        """Soft reset the TS20 and write the full configuration."""
        # Hold the digital block in reset while reconfiguring.  The vendor
        # sequence enters reset with high impedance selected.
        self._write_register(_TS20_GTRL2, self._gtrl2 | _GTRL2_SRST | _GTRL2_IMP_SEL)
        # All ports to capsense (as opposed to LED driver or tact switch)
        for reg in range(_TS20_PORT_CTRL1, _TS20_PORT_CTRL6 + 1):
            self._write_register(reg, 0x00)
        self._write_block(_TS20_SEN_PWM1, self._pack_sensitivity())
        self._write_register(_TS20_GTRL1, self._gtrl1)
        self._write_register(_TS20_CAL_HOLD1, 0x00)  # calibration on, ch 1-7
        self._write_register(_TS20_CAL_HOLD2, 0x00)  # calibration on, ch 8-14
        self._write_register(_TS20_CAL_HOLD3, 0x00)  # calibration on, ch 15-20
        self._write_register(_TS20_ERR_CTRL, self.err_ctrl)
        self._write_register(_TS20_CAL_CTRL, self.cal_ctrl)
        self._write_register(_TS20_GTRL2, self._gtrl2)  # release reset

    def _read_outputs(self) -> int:
        """Read the three Output registers as one bit field.
        Bits 0-19 are pads 0-19, bit 20 is the noise-detect flag.
        """
        b = self._read_block(_TS20_OUTPUT1, 3)
        # Output1 bit7 is reserved/don't-care: mask it so it cannot bleed
        # into pad 7.  Output3 bits 6-7 are empty.
        return (b[0] & 0x7F) | (b[1] << 7) | ((b[2] & 0x3F) << 15)

    def touched(self) -> int:
        """Touch state of all pads as a 20-bit field, bit 0 is pad 0."""
        return self._read_outputs() & 0xFFFFF

    @property
    def touched_pads(self) -> Tuple[bool, ...]:
        """Tuple of 20 booleans, one per pad, True if touched."""
        t = self.touched()
        return tuple(bool(t >> i & 1) for i in range(NUM_PADS))

    def is_touched(self, pad: int) -> bool:
        """True if 'pad' (0-19) is being touched."""
        if pad < 0 or pad >= NUM_PADS:
            raise ValueError("pad must be 0-19")
        return bool(self.touched() >> pad & 1)

    @property
    def noise_detected(self) -> bool:
        """True if the TS20 reports a noisy environment."""
        return bool(self._read_outputs() >> 20 & 1)

    def read_touches(self) -> List[int]:
        """Read back touches, as a list of 21 ints, one per pad plus the
        noise-detect flag last.  Kept for compatibility; new code should
        use 'touched_pads'.
        """
        t = self._read_outputs()
        return [t >> i & 1 for i in range(NUM_PADS + 1)]

    @property
    def sensitivity(self) -> List[int]:
        """Sensitivity of every pad as a 20-element list.
        Set to a single value to change all pads at once, or to a
        20-element list to set them individually.
        0 is most sensitive, 15 is least.
        """
        return list(self._sens)

    @sensitivity.setter
    def sensitivity(self, value: Union[int, Sequence[int]]) -> None:
        self.set_sensitivity(value)

    def set_sensitivity(self, value: Union[int, Sequence[int]], pad: Optional[int] = None) -> None:
        """Set the sensitivity of one pad, or of all pads.

        :param value: 0 (most sensitive) to 15 (least). If 'pad' is None
            this may be a single value for every pad or a 20-element list
            of per-pad values.
        :param pad: pad number 0-19, or None for all pads
        """
        self._store_sensitivity(value, pad)
        self._write_sensitivity()

    def sensitivity_percent(self, pad: int) -> float:
        """The sensitivity setting of 'pad' as the percent change in pad
        capacitance needed to register a touch (datasheet 8.2.1).
        """
        if self.fine_steps:
            return self._sens[pad] * 0.1 + 0.05
        return self._sens[pad] * 0.2 + 0.15

    def read_sensitivity_percent(self, pad: int) -> float:
        """Read back the sensitivity the TS20 currently measures on 'pad',
        in percent.  This is a measurement, not the value set by
        set_sensitivity(), and is useful when tuning per-pad values.
        Blocks for ~150ms per call.

        UNTESTED on hardware.  Datasheet 8.2.11 literally says
        "Sensitivity(%) = SEN_DATA/2048", but an 8-bit SEN_DATA cannot
        reach the 1.15% reset default that way, so SEN_DATA/2048 is read
        here as a fraction and scaled to a percent.
        """
        # SEN_RD_CHANNEL skips code 01000, so channels 8-20 are offset by one
        ch = pad + 1
        self._write_register(_TS20_SEN_RD_CTRL, ch if ch <= 7 else ch + 1)
        time.sleep(0.15)  # tRD, 25ms fast / 130ms slow (datasheet 8.2.10)
        return self._read_block(_TS20_SEN_RD, 1)[0] * 100 / 2048

    def _store_sensitivity(
        self, value: Union[int, Sequence[int]], pad: Optional[int] = None
    ) -> None:
        """Update the shadow copy of the sensitivity values."""
        if pad is not None:
            if pad < 0 or pad >= NUM_PADS:
                raise ValueError("pad must be 0-19")
            self._sens[pad] = value & 0x0F
        elif isinstance(value, int):
            for i in range(NUM_PADS):
                self._sens[i] = value & 0x0F
        else:
            if len(value) != NUM_PADS:
                raise ValueError("sensitivity list must have 20 entries")
            for i, v in enumerate(value):
                self._sens[i] = v & 0x0F

    def _pack_sensitivity(self) -> bytearray:
        """Pack the 20 shadow values into the 11 Sensitivity/PWM registers."""
        for i, (lo_pad, hi_pad) in enumerate(_SENS_NIBBLES):
            hi = _SENS_FILL[i]
            if hi_pad is not None:
                hi = self._sens[hi_pad] << 4
            self._sens_buf[i] = hi | self._sens[lo_pad]
        return self._sens_buf

    def _write_sensitivity(self) -> None:
        """Write the sensitivity registers out to the chip.
        The chip may only latch these across a soft reset, and the reset
        may clear the rest of the register file with them, so do a full
        reset() unless the caller has turned that off.
        """
        if self.reset_on_change:
            self.reset()
        else:
            self._write_block(_TS20_SEN_PWM1, self._pack_sensitivity())
