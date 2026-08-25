Introduction
============


.. image:: https://readthedocs.org/projects/circuitpython-ts20/badge/?version=latest
    :target: https://circuitpython-ts20.readthedocs.io/
    :alt: Documentation Status



.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/todbot/CircuitPython_TS20/workflows/Build%20CI/badge.svg
    :target: https://github.com/todbot/CircuitPython_TS20/actions
    :alt: Build Status


.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
    :target: https://github.com/astral-sh/ruff
    :alt: Code Style: Ruff

Driver for TouchSemi TS20 I2C capacitive touch chip


Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_
* `Bus Device <https://github.com/adafruit/Adafruit_CircuitPython_BusDevice>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.


Installing to a Connected CircuitPython Device with Circup
==========================================================

Make sure that you have ``circup`` installed in your Python environment.
Install it with the following command if necessary:

.. code-block:: shell

    pip3 install circup

With ``circup`` installed and your CircuitPython device connected use the
following command to install:

.. code-block:: shell

    circup install ts20

Or the following command to update an existing version:

.. code-block:: shell

    circup update

Installing from PyPI
=====================
.. note:: This library is not available on PyPI yet. Install documentation is included
   as a standard element. Stay tuned for PyPI availability!

On supported GNU/Linux systems like the Raspberry Pi, you can install the driver locally `from
PyPI <https://pypi.org/project/circuitpython-ts20/>`_.
To install for current user:

.. code-block:: shell

    pip3 install circuitpython-ts20

To install system-wide (this may be required in some cases):

.. code-block:: shell

    sudo pip3 install circuitpython-ts20

To install in a virtual environment in your current project:

.. code-block:: shell

    mkdir project-name && cd project-name
    python3 -m venv .venv
    source .env/bin/activate
    pip3 install circuitpython-ts20


Usage Example
=============

Print out which of the 20 touch pads are being touched:

.. code-block:: python

    import time
    import board
    import ts20

    i2c = board.I2C()  # uses board.SCL and board.SDA

    # sensitivity is 0 (most sensitive) to 15 (least sensitive)
    touch = ts20.TS20(i2c, sensitivity=5)

    while True:
        for pad, is_touched in enumerate(touch.touched_pads):
            if is_touched:
                print("pad", pad, "touched!")
        time.sleep(0.25)

Pads are numbered 0-19 (the datasheet calls them channels CS1-CS20).
Sensitivity is really a touch threshold, so a lower number means the pad
triggers more easily.  It can be changed at any time, for every pad at
once or for a single pad:

.. code-block:: python

    touch.sensitivity = 3       # every pad
    touch[0].sensitivity = 10   # just pad 0, less sensitive
    print(touch.sensitivity)    # list of all 20 settings

See the ``examples`` folder for complete examples.

Documentation
=============
API documentation for this library can be found on `Read the Docs <https://circuitpython-ts20.readthedocs.io/>`_.

For information on building library documentation, please check out
`this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/todbot/CircuitPython_TS20/blob/HEAD/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
