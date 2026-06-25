#!/usr/bin/env python3
"""Thin wrapper — LIFECYCLE moved into the unified periods bundle.

LIFECYCLE used to be inlined as a standalone `const LIFECYCLE = …;` line in
template.html alongside the 6 _PERIODS consts. After externalization
(2026-06-25), all 7 consts live together in /periods/all.js and share a
single content-hash cache-bust. The bundle generator is scripts/inline_periods.py.

This script kept its name + invocation contract so refresh_all.sh and any
existing playbook don't break. It just delegates.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, 'inline_periods.py')])
