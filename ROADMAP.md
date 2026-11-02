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
| A6 | Level dressing: the gates' sky window, glow and electricity; beacons, satellites, signal lights, billboards, comets, space junk, wrecks; the sky's turn matched to the sun | `structures/*/props/jumpgates/*` (skywindow, glow, add, electricity), `scenery/`, level entities | gate and station models, stations.json orbit `skyRotation` | gates' glow, add, electricity and sky window done (2026-11-02: `scene_glb` effects=True, the remake's additive `materials` entries, GoF2/ModGlow; the window's cube, a mip-chained one, baked as GoF3 samples it); the scenery: painted into each orbit's own sky (the user: the skybox only), see below; the sky's turn done (every orbit's `skyRotation`, the strips no longer mirrored) |
| A7 | Loot crates, lore images and texts, boss portraits | `collectables/crates`, `loreimages/` (175), data `LoreElement`, `swf/*Boss*` | crate models, descriptions, portraits | lore texts in (checked 2026-11-02: the Neox Guide's Trim and Porros entries, title + text + image, are the sectors' descriptions the systems build already gives each system's first station; GoF3 has none for Rigant, and its levels carry only a name, no per-hub text). Open: the 175 codex images (the remake's lore panel shows no image), the History / Stories texts, loot crates, boss portraits |

## Gameplay (from the decompilation; each needs remake support)

| # | What | GoF3 (data / systems) | Remake | Status |
|---|---|---|---|---|
| G1 | Devices, about 40: Carom Deflector, EMP generator and projectile, Shield Disruptor, Shield Overcharger (front, sphere), Cluster Module, Proximity Mine, Radar Jammer, Teleport, Engine Booster, Flash Grenade, Loot Magnet, Spark Collector, Mind Control, Cloak, Front Shield, Super Charger, Blast Amplifier, Bomb Spreader, Dynamic Wormhole Generator, wingman devices | `DeviceConfiguration*`, `DeviceBehaviorConfiguration*`, `DeviceUpgradeLevel`, `DeviceSystem`, `DeviceAgentSystem`, `EffectZoneSystem` | the remake's active devices (`device` 136, `Flight.Device`, `PlayerDevices`) and `cloakCooldownMs` | the 8 player devices done: the remake's device system (quick menu, keys 4-6, HUD slots, the NPC slow over multiplayer) and the importer's items (`device_items`: GoF3's sounds, lore-image icons); untested in Play mode; the NPC / boss devices open (G3) |
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
- Done (2026-11-02): the remake's active device system (Modding/README.md "Devices", combat-equipment.md "Devices") and the
  importer's eight items (`DEVICES` in build_gof3_mod.py: GoF3's distances x 11.4, its shield and damage numbers in GoF2's
  scale, the Hiroto Cloak as a cloak with `cloakCooldownMs`). To check in Play mode: each device's feel and numbers (the
  EMP wave's size, the overchargers' damage, the strike charge's 150), the icons' crops. Not done: the other players
  seeing the shots, beams and waves; the deflector against other players; GoF3's device upgrades (levels 1-5).
- NPC / boss devices (teleport, front / back shields, radar jammer, flash grenade, mind control, clones, minions,
  carrier, bomb spreader, wormhole) need an NPC device AI and the bosses as enemies first (G3).

## Level scenery (surveyed 2026-11-02)

GoF3's levels hold 1025 scenery entities beside the stations and gates: border tubes (298), the level's other stations in
the distance (441, scenery/stations), background asteroid rings and clusters (~300), the Mkkt Bkkt entrance gate (111),
parked capital ships as props (57: Hades, the Vossk engineer ships), moons, fog fields, background traffic; small pieces
are few: 5 wrecks, 5 comet groups, 7 armaments, 1 freight container. Decided (the user): no big scenery in the orbits
(GoF3's 20-60 km levels in the remake's ~10 km orbits, and the meshes' cost on phones); then (the user) the skybox only. Done
2026-11-02: each orbit has its GoF3 level's own sky (the remake's orbit "skybox") with the level's scenery beyond 4000
GoF3 units, and what GoF3 hangs on the camera, painted in as seen from the station (sky_scenery: a numpy point-splat
render of each part's diffuse texture, the level's light and fog, at S R^-1 d so it turns with the sky); 59 of 68 orbits
have some, the mod +88 MB. Fog banks, atmospheres, borders, gates, the moons and what lies within 4000 units are left out.
Not seen in game yet; the faces are 512 px, so a distant station is a few pixels.

## Also open from earlier work

- The sky's turn: done 2026-11-02 (gof3_look.sky_rotation, sky_strip.MIRRORED). From libgofm.so: the .ae4texture's faces
  are GL's targets in the order +Y, -X, +Z, +X, -Z, -Y (ae::render::opengl::loadTexture's table), the sky shader samples
  them with the sky mesh's own position (textureCube(EnvironmentMap, normalize(a_position))), and a TransformComponent
  holds a quaternion (TransformSystem::MatrixCache::updateLocal). So the level shows cube direction r at R r, which in the
  remake is S R r (S the x mirror): the strips were mirrored. Now the strip holds the cube at S u, and each orbit's
  "skyRotation" is S R S with R = Rz Ry Rx of the entity's degrees (glm::quat's order: an inference, the loader didn't
  decompile cleanly). Checked offline only (the Euler decomposition rebuilds S R S; the strip equals a GL lookup at S u);
  not seen in game. Earlier, fitting the skies' brightest spots to the levels' lights or sun sprites found no relation
  (GoF3's lights don't follow its skies), so the lights stay as GoF3 places them.
- The second light, ambient colour and planets per level (the remake has no fields for them yet).
- In-game check of the structures' shine (specular strength, normal map orientation) and of Survey Main's foggy sky.
