Galaxy on Fire 3 Ships (mod id gof3_ships), version 2.3

The ships of Galaxy on Fire 3: Manticore for the Galaxy on Fire 2 Unity Remake, as customizable ships (the remake's ship
kits, like the EVERSPACE 2 ships). One ship per GoF3 hull; they are sold by visitors in the Space Lounges (ships.json
"lounge"): in systems of the ship's race, from a story step / rank that grows with the ship's strength, 3 % per bar visit.
The five boss hulls are never sold: pirate bosses fly them, and each drops its own blueprint (below).

Built by gof3_ships_importer (import.py) from the player's own Galaxy on Fire 3 files: the hulls, their paint schemes, the
guns and the game's data.pdb; run it again to rebuild the whole folder (--max-texture 2048 for full-size textures).
source.json lists each ship's data.pdb record, the raw GoF3 values the stats were made from, its turret mounts and skins.

Customize (the hangar, under Inspect ship):
  Skin      every paint scheme of the hull: GoF3's schemes 1-3, Pirate / Huawei where the hull has them, and the data.pdb
            skins that used to be ships of their own in version 1 (Gold, Gr'Gath, R.E.D., Black Red, Atlas II, Grey Shadow,
            Dragon, ...). A skin swaps the hull's textures (and its glass, decal sheet and engine glow where the scheme has
            its own); it changes no stats. The skins load when picked.
  Weapon colour  the energy weapons' and energy turrets' shots in one colour (the remake's Weapon colour row), from GoF3's
            own projectile colours (shipkits.json palette "weapons": the Colorize_Color1 of each GoF3 weapon effect's
            material): Burst Laser violet, Pulse Laser sky blue, Ion Cannon teal, Pirate Ion Cannon red, Plasma Sprayer green,
            EMP blue, Ricochet orange, Scatter Cannon yellow, Amber, White; or Original.
  Weapon models  Shown or Hidden: hidden, the hull flies without its GoF3 guns, their pylons and the turret model (the
            weapons still fire, from the hardpoints themselves; shipkits.json "hardpoints": "toggle").
Guns: the GoF3 guns follow the weapons mounted (shipkits.json "hardpoints"): pulse lasers show the Burst Laser, the M6 beams
the Beam Laser, blasters the Plasma Blast, the Micro Guns and the Scram Cannon the Auto Laser, the railguns the Railgun, the
mass drivers the Mass Driver, the thermo guns the Plasma Focus, the scatter guns the Scatter Plasma, the Disruptor and Dark
Matter lasers the Dismantler; mk1 / mk2 / mk3 by the weapon's rank in its group. They sit on the hull's hardpoints as GoF3
turns them, and the shots leave from their muzzles. Secondaries show nothing (GoF3's launchers have no model).
Turrets: every hull has a turret slot (the boss hulls two) at its GoF3 turret socket, standing on the hull or hanging under
it (hulls without one: on top of the rear half). A turret item mounted there shows a GoF3 turret (a GoF3 weapon mount as
its swivel and the GoF3 gun the item maps to: Hammerhead D1 / D2A2 Auto Laser, L'ksaar Plasma Blast, Berger AGT Mass
Driver, Skuld Railgun, Archimedes Mass Driver mk3, Matador Burst Laser, the plasma collectors the Plasma Focus) instead of
the game's turret models; the item still decides its damage, rate, range, aiming and the plasma stream.

Where each value comes from (the hull's plain data.pdb record, its templates merged):
  name, description   the GuiAttribute text records (English), written as the game's texts write them ("Sh'Gaal")
  race                Identity: Terran 0, Vossk 1, Nivelian 2, pirates 8; the two Inouac ships (Nunam, Kinac) are
                      Midorian (3), GoF2 has no Inouac
  armor               GoF3 hull + shield (GoF3 has no armour pool), log-scaled: 1500 -> 120, 33000 -> 520 (min 100)
  price               the way Galaxy on Fire 2 prices its own ships, fitted to them (the builder's gof2_price_fits, at
                      every build, from the remake's ship tables): equipment slots weigh most, on a curve that flattens
                      at the top (about x1.65 a slot at 5 slots, x1.24 at 14), each primary weapon slot about x1.58, a
                      turret slot x1.11, secondary slots next to nothing, armor only +3 % per 100 (GoF2's armor rises
                      with the slots, so the slots carry its price), cargo and handling a little. Once per economy:
                      "price" for Android, "priceDefault" for the Default Economy (macOS / Windows / iPhone tables, where
                      GoF2's ships cost more). E.g. a 4-gun 14-slot gunship about 4.4-5.5 million (Default 7.4-11
                      million), a 4-gun 12-slot fighter about 2.4-2.6 million, a 2-gun 12-slot boss hull about 1.3 million
  handling            the mean of the Steering turn rates: gunships 95, fighters 114, scouts 155
  slots               primary / secondary: the hardpoints carrying guns / launchers (Arming); turret: the turret mounts;
                      equipment: scout 8, fighter 10, gunship 12, + the DeviceEquip slots (0-2)
  cargo               GoF3 ships have no hold: by class (scout 45 t, fighter 80, gunship 160) and hull length
Size: 53.5 game units per GoF3 unit (the kit's scale; GoF2's Groza is 1231 units long, GoF3's 23.02 units), so the ships
keep their relative sizes; the bosses (Khador Boss, Krotac, Snotch, Sh'Gaal, Bl'Arek, Cronus) are 2200-3200 units long.

Engines: Galaxy on Fire 3's own engine effect (ships.json "engineFx", the remake's EngineFx): at every exhaust a flare
(the white-hot star and its long horizontal streak, brightest seen from behind), a soft cone of crossed cards that fades
as it turns edge-on (from straight behind only the flares show, as in GoF3), and two short streams that waver in smooth
waves and bend behind the ship when it turns, like GoF3's engine trails. Each race's own flare
and exhaust textures (fx/: Nivelian, Terran, Vossk; the Inouac engines borrow the Nivelian ones), GoF3's beam_001 streak for
the streams, all at GoF3's sizes; each exhaust in the colour the model shows at that nozzle (the hull's emissive texture
around the engine helper, tools/engine_glows.py), a skin its own scheme's where it lights them differently. Engines GoF3
scales or turns keep that ("fxScale", "rotation": the Retro's small and large engines, the Vossk hulls' engines angled in).
The Nivelian engines add GoF3's helix: two strands of crackling lightning winding round the exhaust and spinning, in the
deep blue of GoF3's materials, with the streams a dim blue wake under them (the lightning texture is a guess: GoF3's spiral
material names its textures by GUID only). The Terran engines burn in their textures' own amber, as GoF3 shows them (a bright spike with a thin straight streak, no
wavering streams); the Vossk engines the same in teal with lime flares in the nozzles' own colour, their streak as short and
straight as the Terran one. Every exhaust churns as GoF3's do (its exhaust material's flow, at each engine's own
speed: the Terran fast, the Nivelian slow). Nunam and Kinac have no engine helpers: thin cyan exhausts trail from their wing tips
instead, the Nunam's also from its two spike tips, as its concept art shows them. The Nunam flies canopy
first, its spikes trailing, as Fishlabs' concept art draws it (GoF3's model has it the other way round).
Sounds: each ship has GoF3's own engine and boost sounds of its race (the gunships GoF3's shared Asura set, the Inouac
ships the Nivelian one), and the GoF3 guns, rockets and missiles their GoF3 shots and launches.
Speed and boost: each ship flies at GoF3's cruising speed against a fighter's (scouts up to 14 % faster, gunships up to 14 %
slower) and has its class's GoF3 engine booster built in (scouts x3, fighters x2.5, gunships x2 their top speed for
2.9 s, every 12 s); a booster you fit takes its place. The bosses have none, as in GoF3.
Emergency system: the 24 ships GoF3 gives its revive device (Device_Revive_Cloak: destroyed, the ship comes back cloaked
for a moment) have Galaxy on Fire 2's Emergency System built in: the hull's end turns into 10 s of invulnerability, once a
sortie (used up, it is back at the next docking).
Bosses: the Khador Boss, the Krotac, the Snotch, the Sh'Gaal and the Bl'Arek (data.pdb's BossInfo records) are the
pirate bosses' hulls when a pirate event brings a boss (ships.json "traffic": { "boss": true }), every turret mount armed
with their race's heavy turret (the Vossk the L'ksaar, the others the Hammerhead D2A2). Destroying a boss drops its hull's
blueprint in a data container, once (blueprints.json "drops" { "ship" }): the only way to get one.
Most Wanted (wanted.json, characters.json, portraits/): GoF3's 31 campaign bosses are criminals on the Most Wanted boards,
each with its GoF3 portrait, quote, hull and guns: act 1 (Sh'gaal's) on the Vossk boards, act 2 (Khador's) on the
Nivelian ones, act 3 (Ti-Nung's) on the Terran ones, in the campaign and in free play. As in GoF3 the helper bosses come
first, escorted by their two informants' ships, the under bosses once some of them are dead, the big boss last; each
taunts you over the radio with its GoF3 line when found, and the fight plays GoF3's boss music of its act and
rank (music/). Their strength and bounties follow Galaxy on Fire 2's own
boards (7,000-10,000 hull, 60,000-140,000 credits up the ladder) and its difficulty setting; the under and big bosses
drop Golden Cores, and the boss hulls their own blueprint. Eight of them (D'rak, Kl'tark, Rkkt Bkkt, Ica'brn, Vhitarr,
Snotch, Mortak, Surman Rod) lay mines behind them in the fight (Mortak's stay put, the others chase you); each goes
off close by, slowing you; shoot it down first. Mudshark leaves a nanobite cloud behind it that halves your speed
inside it. Khador splits off two clones of itself once hit and opens wormholes behind it that put a chaser right in
front of its guns; Sh'gaal launches five shield drones that make it untouchable until you shoot them down.
Bar missions (events/): four of GoF3's freelance challenges, the ones Galaxy on Fire 2 has nothing like, offered by
visitors in the Space Lounges of every station (now and then, each in about one bar in eight) with Mkkt Bkkt on the
radio: Sprint (twelve checkpoints in order against the clock, each one adding time), Orb Rush (a track of gates with orbs
along it: at least 25 of them, then the finish), Obstacle Race (each gate's orb is shielded until its power nodes are
shot) and Pick-up and Return (orbs scattered around the orbit, carried one at a time to the drop-off zone while raiders
try to stop you). GoF3's other challenges are GoF2's own freelance missions already (Junk removal, Challenge, Intercept,
Defense, Wanted) and are left out. Three of GoF3's distress calls join them: Hijack (shoot the turrets off a stranded
Vossk frigate, then its guards, without destroying it), The Trap (destroy the traps holding a civilian frigate before the
time runs out, past pirate turrets and scouts; then it jumps away) and Errand Boy (stay near each of three distress beacons
while your scanner reads it out, raiders arriving at every one). Siege and Clean Up are GoF2's Protection and Junk
removal and are left out; GoF3's mines aren't in the game.
Three of GoF3's contracts as well: Evacuation (destroy the drones taking freighters apart until their crews are out),
Blackout (stop four waves of bombers before three of them reach a communications relay) and Weapon Control (hack two
satellites by staying close, then stop a stolen weapon transport before it gets away). The relay and the satellites are
GoF3's mining satellite. The other contracts are GoF2's own Protection, Defense, Escort and Recovery missions.
Stash Hunt: a visitor lends you a scanner drone (GoF3's pet drone) that reads out how close three hidden stashes are
until you can see them; smugglers come back for them.
Wingmen: now and then a bar's wingmen fly GoF3 hulls, each with its GoF3 wingman device (Hull Repair mends your hull when
it is low, Ammo Supply restocks your secondary weapon, Charged Shots hit harder for a while), and talk on the radio with
GoF3's wingman lines.
Dogfighting: NPC fighters in GoF3 hulls fight GoF3's way (attack runs that veer off, sitting on your tail, teasing in
front of your nose, leading their shots, barrel-rolling away from hits) and patrol in V formations; Options > Gameplay
"NPC dogfighting" turns it off or gives it to every fighter.
Rifts (encounters.json): the cruise drive now and then finds a rift (from rank 5; the remake sets how often): stages of
raiders, then a boss, here one of GoF3's 31 in its own hull, as strong against the raiders as in GoF3 (its hull + shield over a GoF3 pirate fighter's: 4 to
20 raiders' hulls), flying for its own race with that race's fighters guarding it. With the ES2 Ships mod on too, the rifts stay as frequent and their bosses come from both mods.
Blueprints (blueprints.json): every ship can also be built in the hangar's Blueprints tab, in Galaxy on Fire 2's own way
(its blueprints are items only, so the GoF3 ships follow those): the recipe starts with the product's lower tier, as GoF2's
Wolverine needs a Wolf, here the hull's own GoF3 guns (two, all four for the dearest hulls, of a family of its race, the
mark by its price), then goods and ores of its race's trade, a few ore cores, energy cells and for the dearest a Void
Essence, worth 0.5-0.8 of the ship in odd amounts as GoF2 writes them. Each blueprint is sold by one Space Lounge visitor
at one station of its race (always there, at about 0.35-0.55 of the ship's price, like GoF2's own blueprint sellers) once
the story is past step 16 (any time in free play and multiplayer); the three GoF3 hides in exploration (the Argus, the
K'Ssshar Ka, the Shaan'Ra-Grth) also lie in a derelict to hack at a fixed spot of one orbit. As in GoF3, its race's ships
also drop it now and then (GoF3's chance, at most 5 %), and a boss always drops its own hull's. A blueprint is obtained
once: once you know it, no seller, ship or derelict hands it out again; you can build from it as often as you like.
The view (ships.json "camera", "cockpit", "smoke", "explosionScale"): the cockpit view (F2, or hold the camera button)
sits at GoF3's own cockpit camera point on each hull; a damaged ship smokes and burns from GoF3's two damage points; it
explodes at its GoF3 size (GoF3's fighters as big as GoF2's, the scouts smaller, the gunships and bosses bigger); and the
chase camera is GoF2's for a hull up to 1400 units long, pulled back with a longer hull, and a little further out for the
gunships, as GoF3 places its camera.
Weapons (items.json): GoF3's nine gun families in their three marks are shop items of their own (27 guns: Berger Burst,
Nirai Scatter, Nirai Focus, Loma Dismantler, XCY M-Driver, Nirai P-Blast, Rhoda Auto-L, AMR Railgun, KAT. Beam), named and
described as GoF3 names them. Mark 1 is tech level 3, mark 2 tech level 6, mark 3 tech level 9 (GoF3's mark 3s that share
the mark 2's name are called XN, as GoF3 calls some). On a GoF3 hull each shows its own GoF3 gun; it fires with its GoF3
shot sound, its shots, flash and impact in its GoF3 projectile colour with a short tracer. What carries over from GoF3: the
range class (close 1000 m, medium 1500, long 2000), the projectile speed, the Scatter Plasma's four-shot spread and the Burst
Laser's three-shot burst; the damage per second is GoF2's for the tech level (12 / 24 / 45, more at close range, less at
long range), since GoF3's own damage rises with its upgrade levels and the player's level.
Exhaust styles (exhausts.json): the three GoF3 drives (Nivelian with its helix, Terran, Vossk) on any ship, the game's own
included: the hangar's Customize screen gets an Exhaust row with the drive's two colours (the flare and cone, the trails and
helix), offered in GoF3's engine colours. They sit on the ship's own exhausts and take each nozzle's shape. Each GoF3
hull's exhausts carry their nozzle's outline where it was measured cleanly ("outline", from the glowing nozzle surface), so
other mods' exhausts fit them too.

Capital ships (ships.json "traffic": { "capital" }, the remake's mod capital ships): GoF3's nine large ships at GoF3's own
size, baked from GoF3's structure files (their tiled plating and baked light maps into one texture each, structures/): the
battleships Nemesis (Terran, 4.4 km), Tiamat (Vossk) and Garuda (Nivelian) and the frigates Proteus, Absu and Agni park in
the orbits' capital ship special (Terran and Vossk systems now and then instead of the game's battleships, Nivelian systems,
which have none, in a third of the orbits with freighters), up to 8 of their GoF3 turret points armed with the race's heavy
turret; the freighters Morpheus, Ashnan and Varuna cruise among the orbits' freighters. They come at the Gameplay option
"Mod ships in traffic" (off: none). Never sold.
Kamikazes (ships.json "traffic": { "role": "detonator", "devices" }): GoF3's ramming drones, each race's own model
(Terran, Vossk, Nivelian, pirate), fly among that race's fighters at the same option: they hold their guns and fly into
you to blow up, lay mines behind them that chase you (one every 4 s, 170 m to 1.4 km off) and throw others at you from close
in front (every 5 s), and stop two thirds of your hits from in front with their shield while they close in. Their mines
die to one hit. Never sold.
Mine drops (ships.json "traffic": { "devices" }): as in GoF3, its fighters drop mines behind them once you are seasoned:
from rank 8 a quarter of them sphere mines (a 43 m field for 15 s: the Terran ones drain your shield fast, the Vossk ones
slow you and drain it, the Nivelian and pirate ones eat your hull, at most 5 % a second), from rank 16 biter mines
instead, which chase you and leave you a fifth of your speed for 10 s (shoot them down). A quarter of its gunships
fire GoF3 homing missiles from rank 6 and cluster missiles from rank 18 (ships.json "traffic": { "secondaries" }), at
their own guns' damage.
The Manticore (stations.json "mobile"): GoF3's Hades, the Manticore of GoF3's story, as a moving station that roams every
system: two hours in one (half an hour past each of its stations, so you can leave and come back to it), then another (by the
real clock, so it moves on while you're away). The star map marks where it is and when it leaves. Docked, the system shown is
the one it is in; it stays a Terran ship wherever it goes, its GoF3 engines lit. It has no planet: find it in the orbit it is in, lock it like a station and dock
(the autopilot does too) into its own hangar; it has no Space Lounge. The hangar is GoF3's own Hades hangar (the round
launch pad, the "PMC HADES" walls, the parking bays; GoF3's baked lighting, ships fly in through its open front). Its shop sells up to tech level 10. A launch comes out beside it. Half GoF3's size (6.3 km), since the flight level only draws 15 km far.

From version 1: the paint variants (Groza Gold, Atlas II, ...) are skins of their hull now, not ships: a saved game flying
one gets the remake's usual treatment of a ship that no longer exists (a Phantom and the ship's price back). Their stats
(the Gold tiers' were a little higher) are gone with them.

Models: the GoF3 textures scaled to 1024 px (guns 512). Not included: the five hulls without a ship record in data.pdb
(nivelian_230, terran_007, terran_030, starfox_000, vossk_130).

Ships, guns, textures and texts: Galaxy on Fire 3: Manticore (c) Deep Silver FISHLABS. For personal use.
