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
| A7 | Loot crates, lore images and texts, boss portraits | `collectables/crates`, `loreimages/` (175), data `LoreElement`, `swf/*Boss*` | crate models, descriptions, portraits | lore texts in (checked 2026-11-02: the Neox Guide's Trim and Porros entries, title + text + image, are the sectors' descriptions the systems build already gives each system's first station; GoF3 has none for Rigant, and its levels carry only a name, no per-hub text). Not wanted (the user, 2026-11-02): the codex (the 175 lore images, the History / Stories texts). Boss portraits done with G3. Open: loot crates |

## Gameplay (from the decompilation; each needs remake support)

| # | What | GoF3 (data / systems) | Remake | Status |
|---|---|---|---|---|
| G1 | Devices, about 40: Carom Deflector, EMP generator and projectile, Shield Disruptor, Shield Overcharger (front, sphere), Cluster Module, Proximity Mine, Radar Jammer, Teleport, Engine Booster, Flash Grenade, Loot Magnet, Spark Collector, Mind Control, Cloak, Front Shield, Super Charger, Blast Amplifier, Bomb Spreader, Dynamic Wormhole Generator, wingman devices | `DeviceConfiguration*`, `DeviceBehaviorConfiguration*`, `DeviceUpgradeLevel`, `DeviceSystem`, `DeviceAgentSystem`, `EffectZoneSystem` | the remake's active devices (`device` 136, `Flight.Device`, `PlayerDevices`) and `cloakCooldownMs` | the 8 player devices done: the remake's device system (quick menu, keys 4-6, HUD slots, the NPC slow over multiplayer) and the importer's items (`device_items`: GoF3's sounds, lore-image icons); untested in Play mode; the NPC / boss devices open (G3) |
| G2 | Weapon abilities and buffs: armour piercing, burst hit, shield bypass, chain effect, slowdown; damage / shield drain over time | `Ability*`, `Buff*`, `StrengthAndWeakness` | gun traits | done for the player's weapons 2026-11-02: only two carry abilities (Buffable.onCreationBuffs): the Slowdeath's AbilitySlowdown and the Hunter-XT's AbilityBypassShield, now the remake's slowMs / slowPercent and shieldBypass; GoF3's primaries carry none. The NPC / boss buffs (damage over time, energy drain, StrengthAndWeakness on 43 bosses) wait for G3 |
| G3 | Bosses: info and difficulty, weak points, minions, taunts, portraits | `BossInfo`, `BossSetting`, `BossDifficulty`, `Weakpoint`, `Minion`, `TauntTable` | Most Wanted, capital ship subsystems | Most Wanted done 2026-11-02 (`tools/gof3_wanted.py`, the remake's `wanted.json` with its `escorts` / `taunt` / `music`): the 31 campaign bosses (BossInfo bossType, progressionPosition, infoSource0-2 the informants, quoteSnippet, entourageSnippets; portrait GuiAttribute 1210092) with their hulls, first primary, launcher, portraits as characters, an HB's informants' hulls as its escorts, its first entourage line as its taunt, the HB / UB / BB hierarchy as requiredBounties; strength and bounty by GoF2's rules (the user: GoF2's difficulty, not GoF3's; see "Difficulty: GoF3 against GoF2"); untested in Play mode. Boss music done: each act's and tier's combat_low + combat_high layers from its sector's bank (trim / porros / rigant: annikett, khador, ti_nung) as one 128 s loop, 9 tracks, ~10 MB; GoF3's intensity crossfade, warm-ups and stingers not kept. Open: weak points, the NPC / boss devices and buffs, the events' bosses |
| G4 | Missions: side missions, contracts, distress calls, freelance challenges and seasons (task types kill, escort, find, escape, scan area, protect NPC); story dialogue and actors | `Sidemission`, `ContractSpawnSchedule`, `DistressCallSchedule`, `Freelance*`, `*Task`, `Story*` | bar missions, event graphs | open |
| G5 | Progression: blueprints and parts, ship / weapon / tier upgrades, wingmen and pet drones | `Blueprint*`, `ShipUpgrade*`, `WeaponUpgrade*`, `TierUpgrade`, `Wingman`, `PetDrone` | blueprints.json, wingmen | open |
| G6 | AI: flocking, formations, perception, danger levels, evasive rolls | `FlockingSystem`, `FormationSystem`, `PerceptionSystem`, `AIDangerSystem`, `NPCBanking` | the remake's own (GoF2) AI | open, least needed |


## Difficulty: GoF3 against GoF2 (to look over later)

Decided (the user, 2026-11-02): the GoF3 ships and bosses follow GoF2's difficulty rules, not GoF3's. How the two differ,
from data.pdb and libgofm.so's protobuf descriptors (`BossDifficultyConfig`, `DangerDependentAttributes`, `PowerRatingDeviation`,
`*DangerLevel`, `PlayerLevel`) against the remake's docs/notes/saves.md "Difficulty":

- **One setting against none.** GoF2: a difficulty picked per game (Easy / Normal / Hard / Extreme; the remake's
  `Session.DifficultyFactor` x0.5 / 1 / 1.5 / 2 on NPC hulls and gun damage, raider counts, base guards, the wanted,
  outposts, freelance enemy counts; Extreme's own rules on top). GoF3 has no game-wide difficulty: the world's danger
  rises with the story, and each fight takes its numbers from a danger level.
- **Danger levels 0-40.** Every GoF3 fight has a danger level; `DangerDependentAttributes_<n>` multiplies NPC hull,
  shield and damage by it, per mission kind (grind easy / medium / hard, freelance, distress call, exploration, event
  challenge, boss easy / medium / hard): about 0.06-0.14 at level 1, 2.7-6.3 at 20, 16-38 at 40 (up to 56 for the hard
  grind). GoF2's NPCs differ by ship and by the player's rank (the wanted's +15 x rank hull), not by an orbit level.
- **What spawns.** GoF3 picks NPC ships, weapons, secondaries and devices by danger level and race (`ShipDangerLevel`,
  `WeaponDangerLevel`, `SecondaryWeaponDangerLevel`, `DeviceDangerLevel`: levelFrom-levelTo ranges per `DangerLevelList`).
  GoF2 picks by the system's race and its own tables (`NpcTables`), the gear by tech level and security.
- **Bosses: Normal, Titan, Titan+.** Each boss has three `BossDifficultyConfig`s. Normal: danger level = its place in the
  campaign (1-31), credits and XP 2000-7600, no gate. Titan: danger 30, 3000 credits / 2000 XP, gated by the player's
  power rating (required defence 1300, attack 900); Titan+: danger 40, 5000 / 4000, required 1400 / 1000. A boss is
  "dead" per difficulty: the ladder is replayed at Titan, then Titan+. GoF2's criminals are killed once, at the
  game's difficulty, their bounty fixed (50,000-140,000) and their hull fixed per entry (5000-10000) plus rank.
- **Power rating and pain.** GoF3 rates the player's ship (attack / defence power rating) and compares it with each
  boss config's expected rating: below it, "pain" factors (hullPain, shieldPain, damagePain with their maxima and the
  attack / defence normalizers) make the boss stronger the weaker the player's ship. `PowerRatingDeviation` sets the
  rating window of the grind missions' runs. GoF2 has nothing that looks at the player's ship.
- **Player level and XP.** GoF3's `PlayerLevel` table (XP per level; credits, Mhaan Tiq and revive coins as level
  rewards); bosses and missions give XP. GoF2's rank comes from kills (`Session.Rank`).
- **Mission difficulty.** GoF3's grind missions come as Easy / Medium / Hard (their danger factors above; the scripts'
  "Mission Difficulty" and per-wave "Difficulty Settings"); GoF2's freelance missions scale with the difficulty factor
  and the player's rank.
- **Durability.** A GoF3 boss fight costs ship durability (BossInfo durabilityCost 20); GoF2 has no wear.
- **Premium / China variants.** GoF3's boss configs carry `_premium` columns (other required and expected ratings), its
  player levels `_chn` and `_premium` ones (XP, rewards);
  GoF2 has one table.

What the mods use instead: the bosses' hull 7000 -> 10000 and bounty 60,000 -> 140,000 along each act's ladder (GoF2's
boards), escorts 2-4 (GoF2's 0-4), then the remake's rank bonus and difficulty factor (`TrafficPlan.AddWanted`); the
GoF3 ships' stats were scaled to GoF2's ranges from the start (build_gof3_mod.py, CONVERT).

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
have some, the mod +88 MB. Fog banks, atmospheres, borders, gates and what lies within 4000 units are left out (the moons and other planets:
gof3_world.paint_planets).
Not seen in game yet; the faces are 512 px, so a distant station is a few pixels.

## Also open from earlier work

- Shading (2026-11-02, `tools/gof3_shading.py`, the remake's `_GoF3Params`): approximations left: a ship glass with its own
  specular texture (Terran 000's glass, slot 2) takes only its Specular_Color; a paint scheme with its own multiplier (the
  gold schemes' x 5) keeps its hull's 1.5 for the environment term (its highlight is right); the structure atlases merge
  the solar panels, which GoF3 lets reflect (Environment_Amount), into the no-reflection platings; the capital ships' rim
  is on for the whole baked hull (GoF3: on their largeship parts, off on the platings among them); the weapon mount
  (weapon_generic_mount_000) is still a metallic-roughness material. Checked in game: the Betty II in a hangar and its
  Info preview, the Nemesis in space; the GoF3 Systems mod's stations and gates not seen yet.
- The Manticore hangar (2026-11-02, `tools/hangar_room.py`): baked as GoF3's hangar shader lights it (the regular light
  map: switchHangarLightMap has no caller; the emissive mask; the light map's specular), the pad's orange rim and the light
  strips at the room's glow, the ignition light out (alpha 0 at idle). Not seen in game yet. The structure bakes' light
  map fix (ae4_texture.resized: Pillow scaled RGBA premultiplied) lands with the next full gof3_systems / capitals build.
- The sky's turn: done 2026-11-02 (gof3_look.sky_rotation, sky_strip.MIRRORED). From libgofm.so: the .ae4texture's faces
  are GL's targets in the order +Y, -X, +Z, +X, -Z, -Y (ae::render::opengl::loadTexture's table), the sky shader samples
  them with the sky mesh's own position (textureCube(EnvironmentMap, normalize(a_position))), and a TransformComponent
  holds a quaternion (TransformSystem::MatrixCache::updateLocal). So the level shows cube direction r at R r, which in the
  remake is S R r (S the x mirror): the strips were mirrored. Now the strip holds the cube at S u, and each orbit's
  "skyRotation" is S R S with R = Rz Ry Rx of the entity's degrees (glm::quat's order: an inference, the loader didn't
  decompile cleanly). Checked offline only (the Euler decomposition rebuilds S R S; the strip equals a GL lookup at S u);
  not seen in game. Earlier, fitting the skies' brightest spots to the levels' lights or sun sprites found no relation
  (GoF3's lights don't follow its skies), so the lights stay as GoF3 places them.
- The second light and ambient per level: done 2026-11-02 (the remake's orbit "light2" / "ambient"; 49 orbits have a second
  light, GoF3's light values are already on GoF2's gamma scale). Planets beyond the main one: painted into the
  orbit's sky 2026-11-02 (gof3_world.paint_planets: GoF3's planet shader, a disc at its direction and size; 31 orbits).
- In-game check of the structures' shine (specular strength, normal map orientation) and of Survey Main's foggy sky.
