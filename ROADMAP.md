# What else to pull from Galaxy on Fire 3

The list from the survey of 2026-11-02: GoF3's asset tree, the record and component types of its data (`data.pdb`, named
by the protobuf schema in `libgofm.so`) and its ECS gameplay systems (`syms.txt`), against what `gof3_ships` and
`gof3_systems` already use. Status per item; keep it current as work lands.

Already in: the 37 fighters with their skins, the 27 guns, the turret, the engine effects and sounds, the 9 capital
ships and the Manticore (with its hangar); GoF3's stations, gates (their rotator and rings turning), skies (colours,
stars, fog), suns and each level's light and fog; the structures' own materials (specular, gloss, normal maps).

## Assets (the remake can already use them)

| # | What | From | Into | Status |
|---|---|---|---|---|
| A1 | Secondary weapons: rockets, mines, flak mines, their effects; homing / salvo / smart-bomb arming, ammunition | `weapons/rockets`, `weapons/mines`, `weapons/flak_mines`, data `WeaponSpecification`, `Arming*`, `Ammunition` | `items.json` secondaries | done in the importer: the 7 player missiles (AMR 3X-R, Ketar I-Jet 9T, Berger R-Vortex, AMR Cluster-6, Knos Slowdeath, Nirai Hunter-XT, XCY Smart-Jet X) with GoF3's models, launch sounds and icons; not representable: auto homing (target found in flight), corkscrew / accelerating flight, the slow (an EMP hit stands in), shield bypass, upgrades and magazines per hull class. The mines are NPC-only in GoF3 (flak, biter, sphere mines, smart bombs) and need a remake NPC feature |
| A2 | NPC ships: traders, traffic ships, freighters, mining ships, drones, bombers | `structures/*/geometry/props/{tradingships,trafficships,freight,miningships,drones,bomber}` | `npcships.json` | done in the importer (`gof3_world.py`): the 8 hubs' traffic as freighters, 4 hulls from GoF3's props; GoF3's looping routes not kept (the remake's freighters fly straight) |
| A3 | Planets with atmosphere, rim and corona, aimed as GoF3's levels do | `planets/` (1294 files), level entities on the background camera | per-orbit `planetTexture`, `orbit.planet` | done in the importer (`gof3_planets.py`): 46 orbits, rendered with GoF3's planet shader; horizon-sized planets (over 60 degrees) and partial caps left out |
| A4 | Asteroid fields and ores | data `Field`, `FieldItems`, `OreDistribution`, `OreSpot`, `MiningField`; `asteroids/` | `orbit.asteroids` (count, centre, spread, type, ores) | done in the importer: 48 orbits; one field per orbit, ores by family (Anchorage H4's from GoF3's data) |
| A5 | Music and ambience | `sound/music_hub.bank`, `ambience_stream_*.bank` (FMOD, vgmstream) | the systems' music | done in the importer: each cluster's calm layer (area_arrival1-5) as its systems' `spaceMusic`; combat music and ambience need remake fields |
| A6 | Level dressing: the gates' sky window, glow and electricity; beacons, satellites, signal lights, billboards, comets, space junk, wrecks; the sky's turn matched to the sun | `structures/*/props/jumpgates/*` (skywindow, glow, add, electricity), `scenery/`, level entities | gate and station models, systems.json `skybox.rotation` | planned |
| A7 | Loot crates, lore images and texts, boss portraits | `collectables/crates`, `loreimages/` (175), data `LoreElement`, `swf/*Boss*` | crate models, descriptions, portraits | open |

## Gameplay (from the decompilation; each needs remake support)

| # | What | GoF3 (data / systems) | Remake | Status |
|---|---|---|---|---|
| G1 | Devices, about 40: Carom Deflector, EMP generator and projectile, Shield Disruptor, Shield Overcharger (front, sphere), Cluster Module, Proximity Mine, Radar Jammer, Teleport, Engine Booster, Flash Grenade, Loot Magnet, Spark Collector, Mind Control, Cloak, Front Shield, Super Charger, Blast Amplifier, Bomb Spreader, Dynamic Wormhole Generator, wingman devices | `DeviceConfiguration*`, `DeviceBehaviorConfiguration*`, `DeviceUpgradeLevel`, `DeviceSystem`, `DeviceAgentSystem`, `EffectZoneSystem` | equipment items; the analogues the remake has (cloak, EMP, shield injector, echo blast, mines), new ones where it has none | researched (8 player devices; the rest NPC / boss only); the engine booster's factor fixed (x2 for every class); most need a remake "active device" system |
| G2 | Weapon abilities and buffs: armour piercing, burst hit, shield bypass, chain effect, slowdown; damage / shield drain over time | `Ability*`, `Buff*`, `StrengthAndWeakness` | gun traits | open |
| G3 | Bosses: info and difficulty, weak points, minions, taunts, portraits | `BossInfo`, `BossSetting`, `BossDifficulty`, `Weakpoint`, `Minion`, `TauntTable` | Most Wanted, capital ship subsystems | open |
| G4 | Missions: side missions, contracts, distress calls, freelance challenges and seasons (task types kill, escort, find, escape, scan area, protect NPC); story dialogue and actors | `Sidemission`, `ContractSpawnSchedule`, `DistressCallSchedule`, `Freelance*`, `*Task`, `Story*` | bar missions, event graphs | open |
| G5 | Progression: blueprints and parts, ship / weapon / tier upgrades, wingmen and pet drones | `Blueprint*`, `ShipUpgrade*`, `WeaponUpgrade*`, `TierUpgrade`, `Wingman`, `PetDrone` | blueprints.json, wingmen | open |
| G6 | AI: flocking, formations, perception, danger levels, evasive rolls | `FlockingSystem`, `FormationSystem`, `PerceptionSystem`, `AIDangerSystem`, `NPCBanking` | the remake's own (GoF2) AI | open, least needed |

## Devices: the plan (from the 2026-11-02 research)

- Player devices (GoF3 owns 8 on player ships): Carom Deflector (enemy shots hitting the ship turned back at their
  shooter, x2 damage, 8 s), Hiroto Cloak (10 s, firing allowed), Berger Area EMP (8 s at 25 % speed, can't turn, 800
  units), Berger EMP Projectile (homing, the same slow in 300), DS Shield Disruptor (-2000 shield), Telta S-Wave Area and
  Overcharger Beam (66 % of the shield spent for 0.4 / 0.3 x that as damage), AMR Strike Charge (filled by the ship's
  own hits, then 5 s of x1.75 damage); cooldown 60 s each; the wingmen's First Aid, Ammo Supply and Charged Shots.
- In the remake: the Hiroto Cloak maps onto the cloak items (it needs a `cloakCooldownMs` stat); the rest need an
  "active device" system (an equipment kind fired from the quick menu or a key, its own cooldown and HUD ready state),
  then each device on top of it. Remake work, with Play mode testing.
- NPC / boss devices (teleport, front / back shields, radar jammer, flash grenade, mind control, clones, minions,
  carrier, bomb spreader, wormhole) need an NPC device AI and the bosses as enemies first (G3).

## Also open from earlier work

- The sky's rotation (GoF3 turns each sky entity; the axes into the remake's frame are unchecked), so a sun direction
  doesn't yet line up with its sky's bright side.
- The second light, ambient colour and planets per level (the remake has no fields for them yet).
- In-game check of the structures' shine (specular strength, normal map orientation) and of Survey Main's foggy sky.
