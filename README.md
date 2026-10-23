# Tiny Buddy

A 2D desktop pet for Windows.  Pick a cat or an axolotl, name it, feed it
treats, sit it, make it jump, let it follow your cursor, or put it to work
climbing the sides of the screen and falling back down.

## What you need

* Windows 10 or 11
* Python 3.9 or newer (`py --version` to check)
* Pillow (`pip install pillow`) - the only dependency

## Run it

```
py -m pip install pillow
cd path\to\buddy
py buddy.py
```

or double-click `run.bat`.  The pet appears on the taskbar and starts walking.

## Controls

* **Left click** the pet - opens its action card (Sit, Jump, Follow, Treat, Pet,
  Rename, Colours, Hide).
* **Right click** the pet - the full menu (incl. size, hide, quit).
* **Drag** the pet anywhere, then let go to watch it drop.
* **Ctrl+Alt+B** - show / hide the buddy.
* Click the little paw in the bottom-right corner to bring it back when hidden.
* **Feed a treat** from the card or menu - drops a snack on the work area; the
  buddy walks to it and eats it.

## Behaviour

* The buddy wanders, sits, looks around and every so often walks to a side
  of the screen, climbs up using its (flipped) walking animation, holds on at
  the top for 10 seconds, then drops back to the ground.
* Clicking "Jump" plays the crouching frames as the wind-up and launches it.
* "Follow cursor" makes it walk toward your cursor and sit near it.

## Assets

Sprites: "Cat || Pixel Asset Pack" and "Tiny Axolotl" by Pop Shop Packs
(https://pop-shop-packs.itch.io).  Used inside this project, under their license
(see `assets/CREDITS.md`).  Do not redistribute the loose sprite sheets.
