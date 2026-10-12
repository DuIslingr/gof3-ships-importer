Galaxy on Fire 3 Ships (mod id gof3_ships), version 2

The ships of Galaxy on Fire 3: Manticore for the Galaxy on Fire 2 Unity Remake, as customizable ships (the remake's ship
kits, like the EVERSPACE 2 ships). One ship per GoF3 hull; they are sold by visitors in the Space Lounges (ships.json
"lounge"): in systems of the ship's race, from a story step / rank that grows with the ship's strength, 3 % per bar visit.

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
(the white-hot star and its long horizontal streak, brightest seen from behind), a soft cone of crossed cards, and two long
streams that waver in smooth waves and bend behind the ship when it turns, like GoF3's engine trails. Each race's own flare
and exhaust textures (fx/: Nivelian, Terran, Vossk; the Inouac engines borrow the Nivelian ones), GoF3's beam_001 streak for
the streams, all at GoF3's sizes; each exhaust in the colour the model shows at that nozzle (the hull's emissive texture
around the engine helper, tools/engine_glows.py), a skin its own scheme's where it lights them differently. Engines GoF3
scales or turns keep that ("fxScale", "rotation": the Retro's small and large engines, the Vossk hulls' engines angled in).
The Nivelian engines add GoF3's helix: two strands of crackling lightning winding round the exhaust and spinning, in the
deep blue of GoF3's materials, with the streams a dim blue wake under them (the lightning texture is a guess: GoF3's spiral
material names its textures by GUID only). The Terran engines burn in their textures' own amber, as GoF3 shows them (a bright spike with a thin straight streak, no
wavering streams). Nunam and Kinac have no engine helpers, so no engines.
Exhaust styles (exhausts.json): the three GoF3 drives (Nivelian with its helix, Terran, Vossk) on any ship, the game's own
included: the hangar's Customize screen gets an Exhaust row with the drive's two colours (the flare and cone, the trails and
helix), offered in GoF3's engine colours. They sit on the ship's own exhausts and take each nozzle's shape. Each GoF3
hull's exhausts carry their nozzle's outline ("outline", from the glowing nozzle surface), so other mods' exhausts fit them too.

From version 1: the paint variants (Groza Gold, Atlas II, ...) are skins of their hull now, not ships: a saved game flying
one gets the remake's usual treatment of a ship that no longer exists (a Phantom and the ship's price back). Their stats
(the Gold tiers' were a little higher) are gone with them.

Models: the GoF3 textures scaled to 1024 px (guns 512). Not included: the five hulls without a ship record in data.pdb
(nivelian_230, terran_007, terran_030, starfox_000, vossk_130).

Ships, guns, textures and texts: Galaxy on Fire 3: Manticore (c) Deep Silver FISHLABS. For personal use.
