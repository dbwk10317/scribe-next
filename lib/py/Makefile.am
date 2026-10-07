# scribe-next modification: regenerate the current Python IDL package and force cache refresh.
DESTDIR ?= /
EXTRA_DIST = setup.py scribe

all:

all-local:
	$(MAKE) -C $(top_builddir)/src pythonstyle
	$(PYTHON) setup.py build --force

# We're ignoring prefix here because site-packages seems to be
# the equivalent of /usr/local/lib in Python land.
# Old version (can't put inline because it's not portable).
#$(PYTHON) setup.py install --prefix=$(prefix) --root=$(DESTDIR) $(PYTHON_SETUPUTIL_ARGS)
install-exec-hook:
	$(MAKE) -C $(top_builddir)/src pythonstyle
	$(PYTHON) setup.py build --force install --root=$(DESTDIR) --prefix=$(PY_PREFIX) --record installed_files.txt $(PYTHON_SETUPUTIL_ARGS)

# scribe-next modification: uninstall removes exactly the files the install hook recorded,
# then the package directories they emptied; nothing is looked up through the current Python.
# setup.py strips --root from the recorded paths (leaving them relative for the default "/"),
# so they are resolved under "$(DESTDIR)/" again here (an explicitly empty DESTDIR means "/").
# One path per line; recorded directories that were never created (e.g. __pycache__ when no
# bytecode was written) are skipped.
uninstall-hook:
	test ! -f installed_files.txt || sed 's|^/*||' installed_files.txt | (cd "$(DESTDIR)/" && xargs -r -d '\n' rm -f)
	test ! -f installed_files.txt || sed 's|^/*||; s|/[^/]*$$||' installed_files.txt | sort -ur | (cd "$(DESTDIR)/" && while IFS= read -r d; do test ! -d "$$d" || printf '%s\n' "$$d"; done | xargs -r -d '\n' rmdir --ignore-fail-on-non-empty)
	rm -f installed_files.txt



clean:	clean-local

clean-local:

check-local: all
