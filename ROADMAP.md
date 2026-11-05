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
| A1 | Secondary weapons: rockets, mines, flak mines, their effects; homing / salvo / smart-bomb arming, ammunition | `weapons/rockets`, `weapons/mines`, `weapons/flak_mines`, data `WeaponSpecification`, `Arming*`, `Ammunition` | `items.json` secondaries | done in the importer: the 7 player missiles (AMR 3X-R, Ketar I-Jet 9T, Berger R-Vortex, AMR Cluster-6, Knos Slowdeath, Nirai Hunter-XT, XCY Smart-Jet X) with GoF3's models, launch sounds and icons; not representable: auto homing (target found in flight), corkscrew / accelerating flight, the slow (an EMP hit stands in), shield bypass, upgrades and magazines per hull class. The mines are NPC-only in GoF3 (flak, biter, sphere mines, smart bombs): the bosses' mine layers done 2026-11-05 (see G3); the Kamikaze NPCs done 2026-11-05 (`tools/gof3_kamikaze.py`, the remake's ships.json "traffic": { "devices" }): GoF3's fifth NPC class (ShipType 4, in every race's and the pirates' enemy lists), each race's drone model as a hull its fighters fly (weight 0.5), its ram as the remake's detonator role, its mine layer (one every 4 s, 3420-28500 units off, chasing for 4.5 s), mine thrower (a mine thrown ahead at 4560 a second at a player 570-3420 in front within 30 degrees, every 5 s) and front shield (67 %) as its devices, from the tier-4 records; 68-148 m (the Nivelian one 150, capped for the remake's traffic); GoF3's ram damage (641 per interval in 1516) and tiers not kept; untested in Play mode. The biter / sphere mine drops (SW_NPC_*MineDrop) open |
| A2 | NPC ships: traders, traffic ships, freighters, mining ships, drones, bombers | `structures/*/geometry/props/{tradingships,trafficships,freight,miningships,drones,bomber}` | `npcships.json` | done in the importer (`gof3_world.py`): the 8 hubs' traffic as freighters, 4 hulls from GoF3's props; GoF3's looping routes not kept (the remake's freighters fly straight) |
| A3 | Planets with atmosphere, rim and corona, aimed as GoF3's levels do | `planets/` (1294 files), level entities on the background camera | per-orbit `planetTexture`, `orbit.planet` | done in the importer (`gof3_planets.py`): 46 orbits, rendered with GoF3's planet shader; horizon-sized planets (over 60 degrees) and partial caps left out |
| A4 | Asteroid fields and ores | data `Field`, `FieldItems`, `OreDistribution`, `OreSpot`, `MiningField`; `asteroids/` | `orbit.asteroids` (count, centre, spread, type, ores) | done in the importer: 48 orbits; one field per orbit, ores by family (Anchorage H4's from GoF3's data) |
| A5 | Music and ambience | `sound/music_hub.bank`, `ambience_stream_*.bank` (FMOD, vgmstream) | the systems' music | done in the importer: each cluster's calm layer (area_arrival1-5) as its systems' `spaceMusic`; combat music done 2026-11-05 (the remake's systems.json `battleMusic`, `gof3_world.combat_music`): GoF2's low / medium / full battle tracks from GoF3's combat_low1-3 with its combat_high stems over them at none, half and full (the high layers are stems: 2-11 dB quieter, uncorrelated; MusicHandler's FMOD states "fight" / "fight_heavy"), ~15 MB; the boss tracks now layer the same way (low, then both); stingers, warm-ups and ambience left out; not heard in game |
| A6 | Level dressing: the gates' sky window, glow and electricity; beacons, satellites, signal lights, billboards, comets, space junk, wrecks; the sky's turn matched to the sun | `structures/*/props/jumpgates/*` (skywindow, glow, add, electricity), `scenery/`, level entities | gate and station models, stations.json orbit `skyRotation` | gates' glow, add, electricity and sky window done (2026-11-02: `scene_glb` effects=True, the remake's additive `materials` entries, GoF2/ModGlow; the window's cube, a mip-chained one, baked as GoF3 samples it); the scenery: painted into each orbit's own sky (the user: the skybox only), see below; the sky's turn done (every orbit's `skyRotation`, the strips no longer mirrored) |
| A7 | Loot crates, lore images and texts, boss portraits | `collectables/crates`, `loreimages/` (175), data `LoreElement`, `swf/*Boss*` | crate models, descriptions, portraits | lore texts in (checked 2026-11-02: the Neox Guide's Trim and Porros entries, title + text + image, are the sectors' descriptions the systems build already gives each system's first station; GoF3 has none for Rigant, and its levels carry only a name, no per-hub text). Not wanted (the user, 2026-11-02): the codex (the 175 lore images, the History / Stories texts). Boss portraits done with G3. Loot crates done 2026-11-02 (`tools/gof3_crates.py`, the remake's ships.json "crate", Modding.ModCrates): GoF3's LootPickup box (collectables_002) in its Terran / Vossk / Nivelian platings as those races' ships' crates, the mining one (what GoF3 drops for every enemy) for the rest; fitted to GoF2's container size; not seen in game yet. (collectables/crates/* are the gacha screen's, not loot.) |

## Gameplay (from the decompilation; each needs remake support)

| # | What | GoF3 (data / systems) | Remake | Status |
|---|---|---|---|---|
| G1 | Devices, about 40: Carom Deflector, EMP generator and projectile, Shield Disruptor, Shield Overcharger (front, sphere), Cluster Module, Proximity Mine, Radar Jammer, Teleport, Engine Booster, Flash Grenade, Loot Magnet, Spark Collector, Mind Control, Cloak, Front Shield, Super Charger, Blast Amplifier, Bomb Spreader, Dynamic Wormhole Generator, wingman devices | `DeviceConfiguration*`, `DeviceBehaviorConfiguration*`, `DeviceUpgradeLevel`, `DeviceSystem`, `DeviceAgentSystem`, `EffectZoneSystem` | the remake's active devices (`device` 136, `Flight.Device`, `PlayerDevices`) and `cloakCooldownMs` | the 8 player devices done: the remake's device system (quick menu, keys 4-6, HUD slots, the NPC slow over multiplayer) and the importer's items (`device_items`: GoF3's sounds, lore-image icons); untested in Play mode; the NPC / boss devices open (G3) |
| G2 | Weapon abilities and buffs: armour piercing, burst hit, shield bypass, chain effect, slowdown; damage / shield drain over time | `Ability*`, `Buff*`, `StrengthAndWeakness` | gun traits | done for the player's weapons 2026-11-02: only two carry abilities (Buffable.onCreationBuffs): the Slowdeath's AbilitySlowdown and the Hunter-XT's AbilityBypassShield, now the remake's slowMs / slowPercent and shieldBypass; GoF3's primaries carry none. The NPC / boss buffs (damage over time, energy drain, StrengthAndWeakness on 43 bosses) wait for G3 |
| G3 | Bosses: info and difficulty, weak points, minions, taunts, portraits | `BossInfo`, `BossSetting`, `BossDifficulty`, `Weakpoint`, `Minion`, `TauntTable` | Most Wanted, capital ship subsystems | Most Wanted done 2026-11-02 (`tools/gof3_wanted.py`, the remake's `wanted.json` with its `escorts` / `taunt` / `music`): the 31 campaign bosses (BossInfo bossType, progressionPosition, infoSource0-2 the informants, quoteSnippet, entourageSnippets; portrait GuiAttribute 1210092) with their hulls, first primary, launcher, portraits as characters, an HB's informants' hulls as its escorts, its first entourage line as its taunt, the HB / UB / BB hierarchy as requiredBounties; strength and bounty by GoF2's rules (the user: GoF2's difficulty, not GoF3's; see "Difficulty: GoF3 against GoF2"); untested in Play mode. Boss music done: each act's and tier's combat_low + combat_high layers from its sector's bank (trim / porros / rigant: annikett, khador, ti_nung) as one 128 s loop, 9 tracks, ~10 MB; GoF3's intensity crossfade, warm-ups and stingers not kept. Weaknesses done 2026-11-04 (the remake's wanted.json "damageTaken", `damage_taken`): GoF3 adds damage x (weakness - strength) (StrengthAndWeaknessSystem::modifyDamage); 30 bosses are weak to one family (laser / plasma / ballistic, by the guns' DamageIdentifier), measured from their ordinary guns so GoF2's difficulty holds: +43 % from it (Sh'gaal +15, Khador +56) on GoF2's category for it and the mod's three GoF3 guns of it, 96 % from missiles (Khador 74); the board's text says it; untested in Play mode. Weak points: only the Hulk event boss has them (Left / RightHulkTurret, makesParentInvincible: the remake's capital "shields" objects). Boss devices done 2026-11-04 for 27 bosses (the remake's wanted.json "devices", World.NpcDevices; `devices`): teleport, front / back shield, energy absorber, radar jammer, flash grenade, mind control, bomb spreader with GoF3's durations, cooldowns and triggers; untested in Play mode. Turrets done 2026-11-05 for 17 bosses (the remake's wanted.json "turrets"; `turrets`): GoF3's Backfire / Tank Turrets (EntityAttachment typedAttachments of type 6) as GoF2 turret items by tier (Hammerhead D1; D2A2 or the Vossk L'ksaar; Matador TS) on the hull's own turret mounts, as many as it has (Sh'tare and Ti-Nung 2 of their 4); untested in Play mode. Mine layers done 2026-11-05 for 8 bosses (the remake's device "mineLayer", World.SeekerMine; `mine_layers`): GoF3's ArmingSmartBomb bursts (2 mines 1.5 s apart every 13-18 s, the player 2280-17100 units off) of MovingBomb mines that chase the player, go off within 969 units or after 5 s, blast 1938 units (GoF3's 222-357 damage x 350 / 312.5) and slow by 20 % for 2 s, shootable (60 hull); Mortak's stay put (no speed); Ica'brn's race-static mines left out; untested in Play mode. Mudshark's smart bomb done 2026-11-05 (the remake's device "cloud", World.NpcCloud): its nanobite fog, 5700 units wide for 12 s every 25 s, half speed inside (the speed buff's maxLinearVelocityPostFactor; its turning cut not kept); untested in Play mode. Shadow clones and shielding minions done 2026-11-05 (the remake's devices "shadowClone" / "minions"): Khador's 2 clones on a hit (25 % of its hull + shield each, Ship_A02_BB01_ONLY_FOR_CLONING), Sh'gaal's 5 shield drones every 40 s for 60 s (7 % each, 1140 units out; it takes no hits while one lives); and the act bosses' second records: the importer kept the bigger hull's, which carries no devices, so Khador's teleport and Sh'gaal's front shield and bomb spreader were missing: now all 31 bosses have theirs; untested in Play mode. Khador's dynamic wormhole done 2026-11-05 (the remake's device "wormhole", World.NpcWormhole): a hole 684 units wide 570 behind it for 5 s, with you 1140-2280 off and behind it (GoF3 turns the angle checks on without angles: the remake's 90); flying in puts you 1710 in front of its nose, heading as you were; untested in Play mode. Open: insanity (no lore; DeviceLogicPlayerInsanity didn't decompile cleanly), Mortak's smart bombs (no configuration; its FireBallEffectZone is spawned by nothing), the act bosses' scripted abilities (Sh'gaal, Khador, their "_IGNORE" turrets included), the events' bosses (surveyed 2026-11-05: level-script entities, "Event Boss 01/02" with phases, clones and cutscenes, no data to export) |
| G4 | Missions: side missions, contracts, distress calls, freelance challenges and seasons (task types kill, escort, find, escape, scan area, protect NPC); story dialogue and actors | `Sidemission`, `ContractSpawnSchedule`, `DistressCallSchedule`, `Freelance*`, `*Task`, `Story*` | bar missions, event graphs | freelance done 2026-11-05 (`tools/gof3_missions.py`, see "Missions"): 4 of the 10 challenges as bar missions at every GoF2 station, the other 6 being GoF2's own; distress calls done 2026-11-05: 3 of the 5 (Hijack, The Trap, Errand Boy) the same way, Siege and Clean Up being GoF2's Protection and Junk removal; contracts done 2026-11-05: 3 of the 8 and the 3 contract events (Evacuation, Blackout, Weapon Control), the rest being GoF2's own; untested in Play mode |
| G5 | Progression: blueprints and parts, ship / weapon / tier upgrades, wingmen and pet drones | `Blueprint*`, `ShipUpgrade*`, `WeaponUpgrade*`, `TierUpgrade`, `Wingman`, `PetDrone` | blueprints.json, wingmen | done 2026-11-05 (see "Progression"): GoF2's own systems for the upgrades (the user's choice), GoF3's wingmen (the remake's ships.json "wingmanDevice" and wingmen.json, `tools/gof3_wingmen.py`) and its pet drone (the bar mission Stash Hunt); untested in Play mode |
| G6 | AI: flocking, formations, perception, danger levels, evasive rolls | `FlockingSystem`, `FormationSystem`, `PerceptionSystem`, `AIDangerSystem`, `NPCBanking` | the remake's own (GoF2) AI | done 2026-11-05 (see "AI"): the remake's option "NPC dogfighting" (attack runs, veer-offs, tease, chase, leading shots, evasive rolls) for the mod's hulls (`"traffic": { "ai": "gof3" }`); formations, flocking, bursts and flee left out; untested in Play mode |


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

## Boss devices (surveyed 2026-11-04)

Each campaign boss's DeviceEquip (data.pdb; field names from libgofm.so's protobuf descriptors): a Device (configuration +
behaviour: when it fires) per entry. The behaviour (DeviceBehaviorConfigurationUniversal): on hit, on an interval
(intervalTime, intervalProbability), the player within playerInRangeMin/MaxDist, in / out of an angle, aligned. GoF3 units.

| Device | Bosses | Configuration (non-premium) | Behaviour |
|---|---|---|---|
| FlashGrenade | Vh'arus Tengs, Kl'tark, Bl'arek, T'hebuk, Nheeta (Inan Kazu, Mortak list it) | flashDelay 3 s, flashStrength 10, flashDuration 7 s, duration 1, cooldown 15 | player within 1500, aligned within 80 deg |
| FrontShield | Rkkt Bkkt, Tsun Kha (Sh'gaal, Ti-Nung list it) | duration 10 s, cooldown 10, regenDelay 5 | every 10 s, player within 30 deg ahead |
| BackShield | Reid Sladek, Ica'brn, Surman Rod, Th'ashiik, San-Kabaah, Jodie Millstorm | the same, isBackShield | on hit, every 10 s |
| Teleport | Th'rrshr, Denyse Cadler, Vhitarr, Sh'tare, Korgus Rhena, Dharvok (Khador lists it) | 0.5 s, cooldown 15, min 100 / max 200 radius, minDistanceToPlayer 10, turns toward the player | every 15 s |
| EnergyAbsorberDevice | Ulrus, Sh'orhn, Sh'tare, Jaden Thee, Dharvok | duration 4 s, cooldown 12.5 (dmgToHpRatio unset: 0?) | on hit, then blocked 5 s (deviceBlockTime) |
| RadarJammer | D'rak, Inan Kazu, Snotch, R'hakesh | duration 10 s, cooldown 20 | player within 1500 |
| MindControlDevice | Th'ashiik, Ti-Nung | duration 12 s, cooldown 40 (playerEnemyShieldStop) | on an interval (its time unset) |
| BombSpreaderDevice | Jodie Millstorm (Sh'gaal, Ti-Nung list it) | 6 s, cooldown 30, spreadAngle 45, a bomb every 1.2 s at 100; the owner moves 800 units for 10 s first | player 0-2000, out of angle |
| Device_Active_Insanity | Ti-Nung | 8 s, cooldown 20; "PlayerCloakMakesBossMiss" | player within range |
| Smart Bombs | Mortak | (no configuration) | |

Sh'gaal and Khador (the act bosses) carry none in DeviceEquip; their StrengthAndWeakness lists name their abilities
(Sh'gaal: shielding minions, front shield, bomb spreader; Khador: wormhole, teleport, cloning), done by their levels'
scripts. Turrets (EntityAttachment typedAttachments, type 6, attachedEntity a TurretGroup_* with the race's
bossturret_rotator model and a TW_* gun): a Backfire Turret on 9 bosses (27 per shot, 3 a second in 2-3 s bursts), one or
four Tank Turrets on 8 (17-60 per shot, 2.5-3.5 a second); Sh'gaal's and Khador's are named "_IGNORE". Done 2026-11-05
as GoF2 turret items by tier on the hull's turret mounts (`gof3_wanted.TURRET`).
Done 2026-11-04: the remake's NPC device runner (wanted.json "devices", Modding/README.md "Most Wanted"; combat-equipment.md
"Boss devices") and `gof3_wanted.devices` (by the configuration's type id: the records are named per boss; a back shield
by its flag or "back" in its names; distances x 11.4; the generic back shields' 10,000,000 range dropped). The energy
absorber's dmgToHpRatio is unset in data.pdb: the remake mends half of what it soaks (its default; GoF3's lore: "redirects
this energy into shield regeneration"). Mind control (the player's wingmen turn on them until hit) and the bomb spreader
(the rifts' proximity mines, GoF2's AMR Saber blast) followed the same day. Left: insanity (Ti-Nung: "PlayerCloakMakesBossMiss",
meaning unclear), smart bombs (Mortak, no configuration).

## Missions (surveyed 2026-11-05)

GoF3's ~70 missions are level scripts (Mission: locationEntities, storySnippets, scriptItem, initScript; missionType 0-7):
the campaign's boss levels (2), freelance challenges (3, 7: FM01-FM13 with FreelanceChallenge / Series / Season records),
distress calls (6, 7: DC01 Siege, DC02 Clean Up, DC03 Hijack, DC04 The Trap, DC05 Errand Boy), contracts (1, 0: CM04
Protector, CM05 Emergency Start, CM07 Enforcer, CM08 Weapon Transport), tutorials (4), contract events (Sidemission CE01-03).
Nothing to convert automatically: each is a node graph of CallFunction / OnTimer / Spawn / Task records, so each is
rewritten by hand as a remake mission. The freelance challenges' texts are FT_00-FT_13 (two or three variants per name).

Freelance, against GoF2's freelance types (the user, 2026-11-05: GoF3 has no lounges, so GoF2's stations' pool; add only
what GoF2 hasn't got): Firing Range = Junk removal, Challenger = Challenge, Breakthrough = Intercept, Combat Arena =
Defense / Pirate hunting, Season Boss = Wanted, Tunnel Race = the Sprint without GoF3's laser tubes: left out. Done as the
mod's bar missions (events/gof3_*.gof2mission, offered at every station by a visitor, chance 12 %, Mkkt Bkkt on the
radio): Sprint, Orb Rush, Obstacle Race (the power nodes are held pirate Wasps), Pick-up and Return (raiders every 30 s).
For them the remake gained pickups (/pickup, the mission step "pickup": a glowing orb with its name on the HUD, collected by
an "on near" at its point). Not representable: GoF3's boost rings and the orb's damage while carried.

Distress calls, against GoF2's freelance types: Siege (DC01, waves besieging a freighter) = Protection / Defense, Clean Up
(DC02, toxic waste and its guards) = Junk removal: left out. Done as the mod's bar missions (clients of their own, 12 %):
Hijack (DC03: the mod's npcships.json "hijack_frigate", the Absu with its 8 turret helpers as "Frigate turret" parts that
shield the hull; its "UFOs" four Vossk H'Soc guards; fails should the frigate die), The Trap (DC04: "trapped_frigate", the
Proteus held by the pirates with 4 "Trap" parts shielding it and 3 pirate turrets, 150 s, 3 Wasp scouts; freed, it jumps
away), Errand Boy (DC05, type 0 and without texts of its own in GoF3: three distress beacons as pickups, each scanned by
staying within 400 m for 12 s, the remake's new distance(player, x, y, z); 2, 3, 4 raiders at them). Not representable:
The Trap's mines.

Contracts, against GoF2's freelance types (the texts include CM01-03, which have no mission records: GoF3 runs them as
contract events through Sidemission spawn zones): Cargo Protect (CM01) = Protection, Convoy (CM03, CE03 Support Mkkt
Bkkt) = Escort, Supply Guard (CM04) = Defense, Under Siege (CM05, drones on the Manticore) = Defense, Enforcer (CM07, CE02
Stop the Stolen Freighter) = Recovery / Intercept, CE01 Help Out Keith T. Maxwell left out (in GoF2 the player is Keith).
Done as the mod's bar missions: Evacuation (CM02: two held freighters, held drones taking 0.4 % of a shared hull a second
each, two more every 15 s, 90 s to evacuate), Blackout (CM06, WIP in GoF3: the npcships.json "comm_relay"; four waves of
three bombers that fly to it and vanish there, three hits and it's down), Weapon Control (CM08: two "survey_satellite"s
hacked by staying within 500 m for 10 s, then a pirate freighter flying 80 km to jump out, failed when it gets within 300
m of its exit). The relay and satellites are GoF3's mining satellite (structures/mining/.../satellites/000, its base and
folded wings: structures.convert's new "extra" bodies) as the hull "gof3_satellite", 320 m tall, no traffic.

## Progression (surveyed 2026-11-05)

GoF3's progression is a free-to-play one (XP, timers, skip prices); the user chose GoF2's own systems for it plus what GoF2
lacks. Left to GoF2's: ship upgrades (Thrust / Plating / Reactor / Generator, 5 levels: the Kaamo Club's upgrades, stacking
to 5 by default, on GoF3 hulls too), tier upgrades (T1-T6 of each hull, 900-1500: buying a better ship), weapon and device
upgrades (5 levels of about +3 % accuracy, +2 % fire rate, 1000-6460 credits: the Mk I-III guns the mod makes), blueprints
(already the mod's, GoF2's way). Done: GoF3's wingmen as the bars' (the remake's new ships.json "wingmanDevice" and a mod's
wingmen.json: Modding/README.md "Wingmen"): each hull's device from its tier records' Wingman (28 hulls: 18 Charged Shots,
7 Hull Repair, 3 Ammo Supply; the bosses' none), DeviceConfigurationWingman*'s numbers (repair under 40 % of the hull,
25 % over 3 s; x1.75 for 5 s; 55 s cooldown), 40 % of the wingmen offers, GoF3's radio lines (kill, lost, help, thanks,
warn: 108; the player-death and revive lines left out, GoF2's death ends the flight). The pet drone (PetDrone: detect /
warn distances x ~11, its Gen_secret_stash_* lines) as the bar mission Stash Hunt: three hidden stashes shown only once
very close, readings from a scanner drone flying beside the player, smugglers after the second.

## AI (surveyed 2026-11-05, against the remake's GoF2 AI)

GoF3 (libgofm.so; decompiled dumps /tmp/claude-1000/gof3_ai/*.c, gone with the session): a job stack per NPC
(AIJobComponent) whose jobs set weights on steering behaviours (MoveToTarget, MoveAwayFromTarget, ChasePrey, Tease,
FollowLeader, Flocking, Avoid...). Fighting (AIJob_Fight): only formation leaders pick targets, the best of hostile ones in
sensorRange by 0.5-1 (the attacker budget) x min(1, 1000 / distance) x the angle x playerAttackBonus 1.3; attack runs
(AttackApproach up to ~13 s, then VeerOff 5-6 s away, a 30 % FightIdle of ~2 s at a distance), Tease (flying just ahead of
the player's nose, 4-6 s) and ChasePrey (on its tail at 1.6x speed for 8 s); speed matched to the target head-on. Firing
leads the target (aimingPoint) with an inaccuracy settling from 1 to 0 over 0.5 s, bursts of 4-6 s, 3 s pauses, the best
weapon group by hit chance. AIDanger: an attacker budget, the player's defenseLevel 2 against fighters' attackLevel 1, so
two fighters attack it at a time (bosses, turrets, kamikazes 0: unlimited; a station's harbour 30). NPCBanking: on a hit a
barrel roll (left / right animation stretched to 1.8 s, 1.5 s invulnerable) by chance (fighters 0.33 x the difficulty's
multiplier, capped Easy 0 / Medium 0.15 / Hard 0.25 / Boss 0.66). Flee below half shield and hull (behind a flag nothing
in the data sets). Formations: V (horizontal, mirrored, vertical) and fours, spacing from the leader's radius, followers
stick within 90 units. Difficulty: speed control (Easy 0.33, Medium 0.75), the evade caps, Hard +2.5 % hull / shield and
+4.2 % damage a wave; the danger level only scales hull, shield and damage.

GoF2 (the remake's NpcShip, PlayerFighter::update): every fighter picks (the player first in its list, a 5 s re-roll;
the remake's option "Smarter NPC targeting" is nearest-first with 2 + difficulty attackers a target, GoF3's budget in all
but name), turns at a fixed rate without inertia, fires one gun inside a +-0.0076 cone within 35 000 at the target (no
lead; turrets lead), circles away inside 8000, boosts 5 % of the time every 5 s or after losing 40 % (panic), never rolls
or evades, no formations (only escorts on a freighter, the remake's), no flee. To port, if wanted: the evasive roll on a
hit (the biggest difference in feel), attack runs with veer-offs and tease / chase, leading with settling inaccuracy, V
formations for groups; as an option or for GoF3 hulls only, since they change GoF2's difficulty.
Ported (the user's choice, option 2): the rolls, the attack pattern (runs, veer-offs, hold-backs, tease, chase) and the
lead as Flight.Gof3Dogfight behind Options > Gameplay "NPC dogfighting" (Original / GoF3 on mod hulls, the default / GoF3
for all); every GoF3 hull of the mod's ships.json carries "traffic": { "ai": "gof3" }. GoF3's distances x 11.4.

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
