=====
slurp
=====

Automatic TV show download orchestrator.

**Note**: I do not condone copyright infringement. Please only use
this tool to download material you are legally allowed to download.

What does it do?
----------------

Slurp assists in finding episodes missing from your collection and
instructing your download client to download them automatically.

At the moment, the only available backend is trakt.tv. Slurp will
look at shows on your watchlist or a custom list and check which
episodes do not have the collected flag set. It will then search
1337x.to or torrentleech for the missing episodes and, if found,
instructs deluge to download them. Once the download has completed,
the collected flag for the episode will be set and the file can be
copied or moved to a specified location.

Installation
------------

To install slurp, the easiest way currently is to create a python
virtual environment and install it there: ::

    virtualenv -ppython3 slurp-env
    source slurp-env/bin/activate
    pip install -e https://github.com/iksteen/slurp/archive/master.zip

Usage
-----

To use slurp, first create a configuration file. There's an example
bundled with the source code (slurp.ini-example). By default, slurp
looks for the configuration file in ``$HOME/.config/slurp/slurp.ini``.

If you use the default backend (trakt.tv), slurp will check your
watchlist for shows to complete by default.

Now, you're ready to start slurp. ::

    slurp-env/bin/slurp

Contributing
------------

Contributions are very welcome. Be sure not to copy any code from the
``SickBeard`` project as that project has an incompatible license.

Feel free to `submit issues`_, fork the `repository`_ and feed me your
pull requests!

slurp is published under a `BSD License`_.

.. _`submit issues`: https://github.com/iksteen/slurp/issues
.. _`repository`: https://github.com/iksteen/slurp
.. _`BSD License`: https://github.com/iksteen/slurp/blob/master/LICENSE
