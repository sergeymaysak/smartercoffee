[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

# SmarterCoffee
SmarterCoffee Maker v. 1.0 HA Integration

This is Home Assistant instegration for SmarterCoffee Maker v.1.0

SmarterCoffee Machine v 2.0 is NOT supported and will NOT be supported.

# Installation

- HACS - preffered. 
  - Make sure you have [HACS](https://hacs.xyz) installed
  - Go to HACS/Custom Repositories
  - copy https://github.com/sergeymaysak/smartercoffee into URL field
- Manual - copy contents of custom_components into yours config/custom_components and restart HA

# Supported Features
- auto discovery for HA Config Flow
- trigger start/stop brew
- status: ready, brewing etc
- select amount of cups (from 1 to 12)
- select brew mode - using beans (grinding) or filter style
- select streight of brew (from weak to strong)
- select hot plate minutes (from 5 to 40 minutes)
- detect water level
- detect water presence
- detect carafe presence

# Setup
In your HA UI, go to Configuration/Integrations, select 'Add Integration', search for 'SmarterCoffee Maker' and follow to instructions.
