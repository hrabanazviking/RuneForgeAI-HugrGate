# GLOSSARY OF NORSE PAGAN VIKING TERMS

(GLOSSARY.md)

**Purpose:** Maps Norse mythological terms used throughout the Project A.E.S.I.R. codebase to their technical equivalents. Agents unfamiliar with Norse mythology should consult this document before assuming the meaning of any named component, module, or variable.

**Rule:** Never guess a mythic name's technical function. Always cross-reference this document. If a name is not listed here, it has not yet been catalogued — investigate the source and add an entry.

**Related Documents:** `docs/SYSTEM_VISION.md`, `docs/ARCHITECTURE.md`, `docs/DOMAIN_MAP.md`, `CAPABILITY_LEDGER.md`

---

## How To Use This Glossary

Entries are grouped by mythological domain (Aesir, Runes, Objects, Places, Beings). Each entry contains:

1. **Term** — The exact spelling used in the codebase.
2. **Mythological Origin** — Who or what this refers to in Norse tradition.
3. **Technical Equivalent** — What this name maps to in the software architecture.
4. **Found In** — Which files, modules, or subsystems reference this name.
5. **Notes** — Caveats, ambiguities, or confirmation status.

---

## Section 1: The Aesir (Named Components)

### Æsir

**Mythological Origin:** The principal pantheon of Norse gods — Odin, Thor, Tyr, Baldr, and others. They govern cosmic order, warfare, wisdom, and governance. The word literally means "gods" or "those who govern."

**Technical Equivalent:** The overarching project name. Project A.E.S.I.R. is the umbrella designation for the entire bare-metal Mojo inference engine and its surrounding ecosystem.

**Found In:** Repository name, root documentation, CI pipeline identifiers.

**Notes:** Capitalized as A.E.S.I.R. in documentation. Directory and package references typically lowercase as `aesir` or `aesir_engine`.

---

### Bragi

**Mythological Origin:** The god of poetry and eloquence. Known for his wisdom and fluency of speech. Husband of Iðunn.

**Technical Equivalent:** Unknown or unconfirmed. Likely a component related to output generation, text formatting, or response composition, given Bragi's association with spoken word and verse.

**Found In:** Referenced in project portfolio overview as a named component. Specific module path not confirmed from available documentation.

**Notes:** Needs source verification. An inheriting agent should search `find aesir_engine/ -iname "*bragi*" -o -iname "*braigi*"` and document the actual implementation here.

---

### Eir

**Mythological Origin:** A goddess associated with medical skill, healing, and care. One of Frigg's handmaidens. Represents restoration and recovery.

**Technical Equivalent:** Unknown or unconfirmed. Given the healing association, this may refer to error recovery, retry logic, health-check endpoints, or self-healing/restart mechanisms within the engine.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `eir` in module names, function names, or configuration keys.

---

### Freya

**Mythological Origin:** A Vanir goddess adopted into the Aesir. Associated with love, beauty, fertility, war, and death. Receives half of the slain in her hall, Fólkvangr. Owner of the necklace Brísingamen. A practitioner of seiðr.

**Technical Equivalent:** Unknown or unconfirmed. Given Freya's multifaceted nature (beauty, war, magic), this could map to a rendering/display component, a combat/conflict-resolution routine, or a seiðr-related subsystem. Cannot be narrowed further without source access.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Do not assume function from mythology alone — the codebase may use the name for unrelated reasons.

---

### Heimdallr

**Mythological Origin:** The watchman of the gods. Guards Bifröst, the rainbow bridge connecting Midgard to Asgard. Possesses extraordinary sight and hearing. Will blow the Gjallarhorn to signal Ragnarök. Father of mankind in some sources (Rígsthula).

**Technical Equivalent:** Unknown or unconfirmed. Given Heimdallr's role as sentinel and gatekeeper, this likely maps to a security, authentication, ingress-filtering, or threat-detection component. Possibly the front-door validator for incoming API requests.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. If this is indeed the security/watchman layer, it pairs conceptually with Bifrost (the HTTP bridge), forming the gate-guard relationship seen in the mythology.

---

### Hermóðr

**Mythological Origin:** Son of Odin. Rode to Hel to negotiate Baldr's release from the underworld. The divine messenger and emissary.

**Technical Equivalent:** Unknown or unconfirmed. Given Hermóðr's role as messenger, this may map to IPC messaging, inter-component communication, event dispatch, or notification propagation between engine subsystems.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `hermodr`, `hermundr`, or `hermothr` variants in source tree.

---

### Hœnir

**Mythological Origin:** A god associated with indecision, deliberation, and the act of choosing. Went to the Vanir as a hostage after the Aesir-Vanir war. Known for hesitating and deferring to Mímir's severed head for counsel.

**Technical Equivalent:** Unknown or unconfirmed. Given Hœnir's association with choice and deliberation, this may map to a decision-routing component, sampling-selection logic, or arbitration between conflicting inference paths.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. The mythological pairing of Hœnir and Mímir may mirror a technical pairing where one component proposes and another validates.

---

### Iðunn

**Mythological Origin:** Goddess who tends the golden apples that grant the gods eternal youth. Wife of Bragi.Keeper of rejuvenation and longevity.

**Technical Equivalent:** Unknown or unconfirmed. Given Iðunn's role sustaining vitality, this may map to cache warming, model-refresh logic, session-renewal mechanisms, or periodic-health-task scheduling.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Note the diacritic — searches must account for both `idunn` and `iðunn` orthographies.

---

### Máni

**Mythological Origin:** The personification of the moon. Brother of Sól (the sun). Pursued across the sky by the wolf Hati. Controls lunar cycles and timekeeping.

**Technical Equivalent:** Unknown or unconfirmed. Given Máni's association with cyclical time and illumination in darkness, this may map to a cron-like scheduler, periodic-job executor, or nighttime/off-peak maintenance daemon.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `mani`, `moon`, or lunar-associated identifiers.

---

### Mímir

**Mythological Origin:** A being renowned for unmatched wisdom. Beheaded by the Vanir during the Aesir-Vanir war. Odin preserved the head with herbs and charms, consulting it for counsel. Mímir guards Mímisbrunnr, the Well of Wisdom, beneath the world-tree Yggdrasil. Odin sacrificed an eye to drink from it.

**Technical Equivalent:** Unknown or unconfirmed. Given Mímir's role as oracle and wisdom-keeper consulted by the chief god, this likely maps to a knowledge-base, advisory-subsystem, RAG-backend, or verification layer. The name Mímir-Vörðr in Volmarr's broader ecosystem confirms a verification/truth-governance system bearing this name, though its relationship to the Aesir engine specifically needs clarification.

**Found In:** Referenced in project portfolio overview. Broader ecosystem includes Mímir-Vörðr as a separate concern. Specific module path within Aesir engine not confirmed.

**Notes:** Needs source verification. Distinguish between Mímir-as-Aesir-component and Mímir-Vörðr-as-ecosystem-framework. They may or may not share code.

---

### Óðr

**Mythological Origin:** Husband of Freya. Frequently absent on long journeys, causing Freya to weep tears of red gold. The name means "poetry," "song," or "the frenzied one." Sometimes conflated with Odin, though the relationship is debated.

**Technical Equivalent:** Unknown or unconfirmed. Given the name's association with frenzy, inspiration, and wandering, this may map to a speculative-decoding component, a stochastic-search routine, or a creative/explorative generation mode.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `odr`, `othr`, or ASCII-folded variants.

---

### Sól

**Mythological Origin:** The personification of the sun. Sister of Máni. Pursued across the sky by the wolf Sköll. Illuminates the world.

**Technical Equivalent:** Unknown or unconfirmed. Given Sól's role as primary illuminator, this may map to a logging/dashboard/visualization component, a primary-output formatter, or a daytime/on-peak processing mode.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Paired conceptually with Máni (sun/moon duality).

---

### Skaði

**Mythological Origin:** A giantess who married the sea god Njörðr as restitution for the killing of her father Þjazi. Goddess of skiing, hunting, winter, and mountains. Desired a husband by picking feet — chose Njörðr by mistake, intending Baldr. The marriage failed due to incompatible habitat preferences (mountains vs. coast).

**Technical Equivalent:** Unknown or unconfirmed. Given Skaði's associations with cold, hunting, and rugged terrain, this may map to a cold-path/cache-miss handler, a sparse-resource optimizer, or an adversarial/threshold-tuning component that "hunts" for optimal parameters.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `skadi`, `skaði`.

---

### Ullr

**Mythological Origin:** God of hunting, archery, skiing, and single combat. Son of Sif, stepson of Thor. Associated with oaths taken on rings and duels. Said to be so skilled that men invoked his name in single combat.

**Technical Equivalent:** Unknown or unconfirmed. Given Ullr's precision and single-target focus, this may map to a single-shot inference path, a targeted/token-specific optimization, or a precision-focused profiler.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `ullr`.

---

### Víðarr

**Mythological Origin:** Son of Odin and the giantess Gríðr. The Silent God. Nearly as strong as Thor. Destined to kill Fenrir at Ragnarök by tearing the wolf's jaws apart — aided by a specially reinforced shoe. Survives Ragnarök.

**Technical Equivalent:** Unknown or unconfirmed. Given Víðarr's role as the one who defeats the apocalyptic beast through patient preparation and singular decisive action, this may map to a crisis-handler, OOM-killer override, emergency-stop mechanism, or catastrophe-recovery subroutine.

**Found In:** Referenced in project portfolio overview. Specific module path not confirmed.

**Notes:** Needs source verification. Search for `vidarr`, `vitharr`, `viðarr`.

---

## Section 2: Runes (Masking Scheme)

### Elder Futhark

**Mythological Origin:** The oldest form of the runic alphabet, consisting of 24 characters. Used across Scandinavia and Germanic Europe from approximately the 2nd to 8th centuries CE. Each rune carries a phonetic value and a symbolic/esoteric meaning.

**Technical Equivalent:** The naming scheme for the engine's masking/configuration system. Individual runes serve as identifiers or toggles for specific masking behaviors applied to logits during sampling.

**Found In:** Masking Seidr subsystem, configuration files, logit-mask identifiers.

**Notes:** The README confirms a "full Elder Fūþark masking scheme" but does not enumerate which runes map to which masks. This mapping must be extracted from source and appended below.

---

### Rune-to-Mask Mapping (CONFIRMATION NEEDED)

The following table is a TEMPLATE. An agent with source access must populate it by extracting the actual rune-to-behavior mappings from the Masking Seidr implementation.

| Rune | Name | Phonetic | Probable Mask Behavior | Confirmed |
|------|------|----------|------------------------|-----------|
| ᚠ | Fehu | F | Unknown — wealth/provision theme may map to token-budget control | NO |
| ᚢ | Uruz | U | Unknown — strength/theme may map to confidence-floor enforcement | NO |
| ᚦ | Thurisaz | TH | Unknown — thorn/giant theme may map to adversarial-input blocking | NO |
| ᚨ | Ansuz | A | Unknown — Odin/message theme may map to system-prompt locking | NO |
| ᚱ | Raidho | R | Unknown — journey/order theme may map to sequence-flow control | NO |
| ᚲ | Kenaz | K | Unknown — torch/knowledge theme may map to entropy-clamp or beam-width | NO |
| ᚷ | Gebo | G | Unknown — gift/exchange theme may map to reciprocity-weighted sampling | NO |
| ᚹ | Wunjo | W | Unknown — joy/perfection theme may map to quality-score gating | NO |
| ᚺ | Hagalaz | H | Unknown — hail/disruption theme may map to dropout/stochastic-noise injection | NO |
| ᚾ | Nauthiz | N | Unknown — need/constraint theme may map to hard-max-token-limit enforcement | NO |
| ᛁ | Isa | I | Unknown — ice/stasis theme may map to temperature-zero lockdown | NO |
| ᛃ | Jera | J | Unknown — harvest/cycle theme may map to periodic-flush or epoch-marking | NO |
| ᛇ | Eihwaz | EI | Unknown — yew/endurance theme may map to context-window-extension guard | NO |
| ᛈ | Perthro | P | Unknown — fate/luck theme may map to stochastic-temperature modulation | NO |
| ᛉ | Algiz | Z | Unknown — elk/protection theme may map to safety-filter activation | NO |
| ᛋ | Sowilo | S | Unknown — sun/victory theme may map to best-of-N selection | NO |
| ᛏ | Tiwaz | T | Unknown — justice/oath theme may map to constraint-violation detection | NO |
| ᛒ | Berkano | B | Unknown — birch/rebirth theme may map to context-reset or re-initialization | NO |
| ᛖ | Ehwaz | E | Unknown — horse/partnership theme may map to dual-model handshake | NO |
| ᛗ | Mannaz | M | Unknown — humanity/self theme may map to persona-lock enforcement | NO |
| ᛚ | Laguz | L | Unknown — water/flow theme may map to sliding-window/context-shift | NO |
| ᛜ | Ingwaz | NG | Unknown — gestation/storage theme may map to cache-commit or persistence | NO |
| ᛟ | Othalan | O | Unknown — inheritance/property theme may map to model-config inheritance | NO |
| ᛞ | Dagaz | D | Unknown — daylight/awakening theme may map to wake-from-idle or warm-restart | NO |

**Procedure for population:**
1. Locate the Masking Seidr source file (likely `aesir_engine/engine/masking_seidr.mojo` or similar).
2. Find the rune identifier constants or enums.
3. For each rune, trace the mask function it activates.
4. Document the exact behavior, not the mythological guess.
5. Mark the "Confirmed" column YES.
6. Delete the probable-behavior column once all entries are confirmed from source.

---

## Section 3: Objects And Artifacts

### Bifröst

**Mythological Origin:** The rainbow bridge connecting Midgard (the human world) to Asgard (the realm of the gods). Guarded by Heimdallr. Will shatter under the weight of the giants during Ragnarök.

**Technical Equivalent:** The HTTP/API bridge component (named BifrostGate in the codebase). Connects external callers (Midgard — the outside/client world) to the inference engine interior (Asgard — the privileged compute core).

**Found In:** `BifrostGate` referenced as the bare-metal HTTP server. Module path likely `aesir_engine/server/` or `aesir_engine/gateway/`.

**Notes:** CONFIRMED from README. The Midgard→Asgard traversal maps cleanly to the client→engine request path.

---

### Brísingamen

**Mythological Origin:** The legendary torc-necklace owned by Freya. Forged by four dwarves (the Brisings). She obtained it by sleeping with each dwarf in turn. A symbol of irreducible value and negotiated exchange.

**Technical Equivalent:** Unknown or unconfirmed. May map to a premium-feature unlock, a cryptographic-key store, or a licensing/access-tier mechanism.

**Found In:** Not confirmed in available documentation. Search source for `brisingamen`, `brisings`, or `torc`.

**Notes:** Needs source verification. May not exist as a codebase identifier — included here proactively in case agents encounter it.

---

### Draupnir

**Mythological Origin:** Odin's enchanted gold ring, forged by the dwarves Eitri and Brokkr. Every ninth night, it drips eight identical copies of itself. A symbol of multiplicative wealth and self-replication.

**Technical Equivalent:** Unknown or unconfirmed. Given the self-replicating property, this may map to a fork/spawn mechanism, a batch-expansion routine, or a model-instance cloning facility for parallel inference.

**Found In:** Not confirmed. Search source for `draupnir`, `ring`, or replication-associated identifiers.

**Notes:** Needs source verification. Included proactively.

---

### Gjallarhorn

**Mythological Origin:** Heimdallr's sounding horn. Stored at the roots of Yggdrasil until Ragnarök. When blown, it alerts all beings that the end is coming. A warning instrument of irreversible significance.

**Technical Equivalent:** Unknown or unconfirmed. Given the alarm/alert function, this likely maps to a critical-alert system, a fatal-error broadcaster, or a shutdown-initiate signal propagated across all engine subprocesses.

**Found In:** Not confirmed. Search source for `gjallarhorn`, `alarm`, `alert_horn`, or shutdown-signal identifiers.

**Notes:** Needs source verification. If this exists, it is the engine's emergency-broadcast mechanism.

---

### Gleipnir

**Mythological Origin:** The silken fetter forged by dwarves to bind Fenrir. Made from six impossible ingredients: the sound of a cat's footfall, the beard of a woman, the roots of a mountain, the sinews of a bear, the breath of a fish, and the spit of a bird. The only restraint strong enough to hold the Wolf until Ragnarök.

**Technical Equivalent:** Unknown or unconfirmed. Given Gleipnir's role as an engineered restraint for a dangerous force, this may map to a sandbox/container-boundary enforcement, a resource-quota limiter, or a safety-constraint solver that binds rogue processes.

**Found In:** Not confirmed. Search source for `gleipnir`, `fetter`, `bind`, or containment identifiers.

**Notes:** Needs source verification.

---

### Gram

**Mythological Origin:** The sword of the hero Sigurd (Siegfried), used to slay the dragon Fafnir. Forged by the smith Regin. Reforged after being broken. A weapon of singular decisive power.

**Technical Equivalent:** Unknown or unconfirmed. Given Gram's role as a singular decisive weapon, this may map to a one-shot optimization pass, a decisive-kill function for hung processes, or a precision surgical-edit tool for model weights.

**Found In:** Not confirmed. Search source for `gram`, `sword`, or refactor/edit identifiers.

**Notes:** Needs source verification.

---

### Gungnir

**Mythological Origin:** Odin's spear. Never misses its target. Sworn oaths are sealed upon its point. Carved with runes. A weapon of absolute precision and binding authority.

**Technical Equivalent:** Unknown or unconfirmed. Given Gungnir's unerring-accuracy property, this may map to an exact-match resolver, a deterministic-routing function, or a commit/merge-lock enforcement mechanism.

**Found In:** Not confirmed. Search source for `gungnir`, `spear`, or targeting/resolution identifiers.

**Notes:** Needs source verification.

---

### Megingjörð

**Mythological Origin:** Thor's belt of strength. Doubles his already considerable power. Necessary for wielding Mjölnir effectively.

**Technical Equivalent:** Unknown or unconfirmed. Given the power-amplification property, this may map to a turbo/overclock profile, a batch-processing accelerator, or a compute-offload coordinator that doubles throughput.

**Found In:** Not confirmed. Search source for `megingjord`, `belt`, or acceleration identifiers.

**Notes:** Needs source verification. ASCII folding may render as `megingjord`.

---

### Mjölnir

**Mythological Origin:** Thor's hammer. Forged by dwarves with a shortened handle due to Loki's sabotage. Returns to Thor's hand when thrown. Channels lightning. Sanctifies marriages, protections, and oaths. The supreme weapon of the thunder god.

**Technical Equivalent:** Unknown or unconfirmed. Given Mjölnir's role as the primary strike weapon that returns to its wielder, this may map to a primary-execution kernel, a recurrent-call optimization, or the main inference-hotloop itself.

**Found In:** Not confirmed. Search source for `mjolnir`, `hammer`, or primary-kernel identifiers.

**Notes:** Needs source verification.

---

### Skíðblaðnir

**Mythological Origin:** Freyr's magical ship. Always sails with a favorable wind. Can fold up like cloth and be carried in a pouch. Carries all the gods with their weapons. The ultimate portable vehicle.

**Technical Equivalent:** Unknown or unconfmed. Given Skíðblaðnir's portability and deployability, this may map to a portable-binary packager, a container-image builder, or a deployment-bundle system that folds the engine into a distributable artifact.

**Found In:** Not confirmed. Search source for `skidbladnir`, `skip`, `fold`, or packaging identifiers.

**Notes:** Needs source verification. The mythological emphasis on portability aligns with the project's local-first/deploy-anywhere ethos.

---

## Section 4: Places And Cosmic Geography

### Ásgarðr

**Mythological Origin:** The fortified citadel of the Aesir gods. Located at the crown of the cosmos. Reachable only via Bifröst. Contains the halls of the gods (Valhöll, Gladsheimr, etc.). Seat of divine governance.

**Technical Equivalent:** The engine's privileged compute core. The interior sanctum of the inference pipeline, reachable only through BifrostGate (the HTTP bridge). Analogous to kernel-space or the protected runtime environment.

**Found In:** Conceptual architecture. May appear in configuration namespaces or privilege-level identifiers.

**Notes:** Maps inversely to Miðgarðr (below). The Asgard↔Midgard axis is the engine-interior↔caller-exterior boundary.

---

### Miðgarðr

**Mythological Origin:** The middle enclosure. The world inhabited by humans. Surrounded by an impassable ocean and the serpent Jörmungandr. Connected to Asgard by Bifröst. Protected from the giants by the wall built from Ymir's skull.

**Technical Equivalent:** The external caller environment. Client applications, API consumers, anything outside the engine's privileged runtime. The "outside world" from the engine's perspective.

**Found In:** Conceptual architecture. May appear in network-isolation configs, ACL scopes, or request-origin classifiers.

**Notes:** Pairs with Ásgarðr to define the trust boundary.

---

### Útgarrðr

**Mythological Origin:** The outer enclosure. The stronghold of Utgard-Loki, the trickster giant king. A place where perceptions deceive and scale is distorted. Thor's illusions-defeating journey took place here.

**Technical Equivalent:** Unknown or unconfirmed. Given Útgarrðr's association with deception and the untrusted exterior, this may map to adversarial-input quarantine zones, honeypot receivers, or untrusted-network partitions.

**Found In:** Not confirmed. Search source for `utgardr`, `utgart`, `outer_enclosure`, or quarantine-zone identifiers.

**Notes:** Needs source verification.

---

### Valhöll

**Mythological Origin:** The Hall of the Slain. Odin's residence in Asgard. Warriors killed in battle (einherjar) are brought here by valkyries. They fight all day and feast all night until Ragnarök. Five hundred forty doors. Roofed with shields. Spear-shaft rafters. A goat (Heiðrún) feeds them mead from her udder.

**Technical Equivalent:** Unknown or unconfirmed. Given Valhöll's role as a staging-ground for accumulated warriors awaiting final deployment, this may map to a request-backlog queue, a completed-session archive, or a worker-thread resurrection pool.

**Found In:** Not confirmed. Search source for `valhalla`, `valholl`, `hall`, or queue/archive identifiers.

**Notes:** Needs source verification.

---

### Yggdrasill

**Mythological Origin:** The World Tree. The cosmic ash that structures all of reality. Its roots penetrate three wells (Urdarbrunnr, Mímisbrunnr, Hvergelmir). Its branches shelter the Nine Worlds. An eagle nests in its crown. The serpent Niðhöggr gnaws its roots. The Norns tend it daily. It suffers eternally yet persists.

**Technical Equivalent:** Unknown or unconfirmed within the Aesir engine specifically. In Volmarr's broader ecosystem, Yggdrasil names a distributed-inference system (Yggdrasil-Distributed-Inference-System) that pools models across devices. Whether the Aesir engine itself contains an internal Yggdrasil-branded component (distinct from the separate project) is unclear.

**Found In:** Possible conceptual reference in architecture docs. Definitely exists as a sibling project in the portfolio.

**Notes:** DO NOT conflate the Yggdrasil-Distributed-Inference-System (separate repo) with any internal Aesir component that may coincidentally share the name. Verify before documenting.

---

## Section 5: Beings And Creatures

### Einherjar

**Mythological Origin:** The chosen slain. Warriors gathered from battlefields by valkyries and brought to Valhöll. They fight endlessly, die, rise again, and feast. Odın's army for Ragnarök.

**Technical Equivalent:** Unknown or unconfirmed. Given the einherjar's nature as resurrectable fighters deployed in waves, this may map to worker processes that respawn after crashing, or pooled inference workers recycled between requests.

**Found In:** Not confirmed. Search source for `einherjar`, `chosen_slain`, or worker-pool identifiers.

**Notes:** Needs source verification.

---

### Fenrir

**Mythological Origin:** The monstrous wolf son of Loki and Angrboa. Foretold to kill Odin at Ragnarök. Bound by the gods using Gleipnir after breaking all lesser chains. Bites off Tyr's hand during the binding. A force of apocalyptic destruction held in check by engineered restraint.

**Technical Equivalent:** Unknown or unconfirmed. Given Fenrir's role as a contained-apocalypse, this may map to a capped/explosive-load-test simulator, a deliberately-dangerous fuzz-test corpus, or a throttle-controlled stress-spawner used in QA.

**Found In:** Not confirmed. Search source for `fenrir`, `wolf`, or stress/test identifiers.

**Notes:** Needs source verification. If Fenrir exists in the codebase, Gleipnir (above) is probably its restraint mechanism.

---

### Jörmungandr

**Mythological Origin:** The World Serpent. Son of Loki. Cast into the ocean by Odin, where it grew until it encircled Midgard, biting its own tail. A symbol of encompassing, self-consuming totality. Thor fishes for it. They are destined to kill each other at Ragnarök.

**Technical Equivalent:** Unknown or unconfirmed. Given the ouroboros imagery, this may map to a ring-buffer, a circular-cache implementation, or a full-context-wraparound handler for sequences approaching the model's maximum context length.

**Found In:** Not confirmed. Search source for `jormungandr`, `ouroboros`, `serpent`, or ring-buffer identifiers.

**Notes:** Needs source verification.

---

### Níðhöggr

**Mythological Origin:** The serpent-dragon that dwells at the roots of Yggdrasil, chewing at the tree's foundation. Feeds on corpses in Náströnd. A corrosive force attacking the structure that holds the world together.

**Technical Equivalent:** Unknown or unconfirmed. Given Niðhöggr's role as a corrosive attacker of foundational structure, this may map to a corruption-detector probing model weights, a fuzz-tester attacking tensor integrity, or a memory-leak hunter gnawing at allocation foundations.

**Found In:** Not confirmed. Search source for `nidhoggr`, `nihoggr`, `dragon`, or corruption-detect identifiers.

**Notes:** Needs source verification.

---

### Sleipnir

**Mythological Origin:** Odin's eight-legged steed. Fastest of all horses. Foaled by Loki (in mare form) after mating with the giant stallion Svaðilfari. Travels between worlds. Bears Odin to Hel to consult Mímir's head.

**Technical Equivalent:** Unknown or unconfirmed. Given Sleipnir's unparalleled speed and world-spanning mobility, this may map to a high-throughput transport layer, an RPC-fastpath, or a multi-channel parallel-I/O dispatcher.

**Found In:** Not confirmed. Search source for `sleipnir`, `steed`, `transport`, or RPC identifiers.

**Notes:** Needs source verification.

---

### Valkyrjur (Valkyries)

**Mythological Origin:** Female warrior-spirits who ride over battlefields selecting which warriors die and which live. Servants of Odin. They bring the chosen slain to Valhöll. Their name means "choosers of the slain."

**Technical Equivalent:** Unknown or unconfirmed. Given the valkyries' role as selectors who pick winners from a field, this may map to a sampling-selector function, a top-k/nucleus-sampling implementation, or a request-admission controller deciding which requests enter the inference pipeline.

**Found In:** Not confirmed. Search source for `valkyrie`, `chooser`, or sampling/admission identifiers.

**Notes:** Needs source verification. If this exists, it may be closely coupled with the stateless sampler component.

---

## Section 6: Concepts And Forces

### Seiðr

**Mythological Origin:** A form of magic and sorcery practiced in Norse society, particularly associated with Freya, who taught it to Odin. Involves prophecy, shapeshifting, cursing, healing, and manipulating fate. Considered ergi (socially taboo for men) in some sources, yet Odin practiced it anyway, accepting shame for power.

**Technical Equivalent:** Appears in the codebase as "Masking Seidr" — the logit-masking subsystem that shapes and constrains the probabilistic output of the model. The metaphor maps seiðr's fate-manipulation to the engine's probability-manipulation through masked sampling.

**Found In:** Masking Seidr subsystem. Likely located at `aesir_engine/engine/masking_seidr.mojo` or similar path.

**Notes:** CONFIRMED from README. The seiðr→logit-masking mapping is explicit in the project description.

---

### Örlǫg

**Mythological Origin:** "Original law" or "primordial layers." The accumulated consequences of past actions that shape an individual's or a people's destiny. Distinct from but intertwined with wyrd. The foundation upon which fate is built. What you inherit from ancestors and prior choices.

**Technical Equivalent:** Unknown or unconfirmed within the Aesir engine. In Volmarr's broader ecosystem, Ørlög names a chrono-biological/emotional-state engine for AI companions. Whether the Aesir engine contains an internal ørlǫg-branded component is unclear.

**Found In:** Not confirmed within Aesir engine source. Exists as a concept in sibling projects.

**Notes:** Needs source verification. Do not assume the sibling-project meaning transfers to this codebase.

---

### Vörðr

**Mythological Origin:** A watcher, guardian, or ward. A protective spirit or sentinel. Related to the verb "to guard." Implies vigilance and defensive oversight.

**Technical Equivalent:** Appears in the broader ecosystem as Mímir-Vörðr ("Warden of the Well") — a RAG/verification/hallucination-control system. Whether the Aesir engine contains a separate vörðr component is unconfirmed.

**Found In:** Mímir-Vörðr exists as a sibling concept. Aesir-internal usage unconfirmed.

**Notes:** Needs source verification. Distinguish between ecosystem-level and engine-local usage.

---

### Wyrd

**Mythological Origin:** The fundamental concept of fate and destiny in Norse cosmology. Not predetermined in the simple sense — it is the unfolding of reality shaped by örlǫg, choices, and the Norns' weaving. All beings, including gods, are subject to wyrd. It is what happens, necessarily, given everything that came before.

**Technical Equivalent:** Unknown or unconfirmed within the Aesir engine. In the broader ecosystem, WYRD Protocol names an ECS-style deterministic world-modeling system. Whether the Aesir engine contains an internal wyrd-branded component is unclear.

**Found In:** Not confirmed within Aesir engine source. Exists prominently in sibling projects.

**Notes:** Needs source verification. The word "wyrd" may appear casually in documentation without denoting a branded component.

---

## Section 7: Structural Terminology

### Hof

**Mythological Origin:** A Norse temple or shrine. A enclosed sacred space for communal ritual. Distinct from the vé (sacred enclosure outdoors).

**Technical Equivalent:** Unknown or unconfirmed. May designate a top-level organizational grouping in the codebase — analogous to a "namespace" or "crate."

**Found In:** Not confirmed. Search source for `hof` in directory names or module declarations.

**Notes:** Needs source verification.

---

### Vé

**Mythological Origin:** A sacred enclosure. One of the three sons of Buri (with Odin and Vili) who participated in the creation of the world from Ymir's body. Also denotes a consecrated outdoor space for worship.

**Technical Equivalent:** Unknown or unconfirmed. May designate a submodule, a configuration scope, or a designated initialization zone within the engine.

**Found In:** Not confirmed. Search source for `ve`, `vé`, or sacred-space identifiers.

**Notes:** Needs source verification. Beware collision with the Spanish conjunction "ve" or the mathematical notation.

---

## Confirmation Tracker

| Category | Total Entries | Confirmed From Source | Needs Verification | Fully Unmapped |
|----------|---------------|----------------------|--------------------|----|
| Aesir (Named Components) | 15 | 0 | 0 | 15 |
| Runes (Masking Scheme) | 24 | 0 | 24 (template pending) | 0 |
| Objects and Artifacts | 10 | 0 | 0 | 10 |
| Places and Cosmic Geography | 5 | 0 | 0 | 5 |
| Beings and Creatures | 6 | 0 | 0 | 6 |
| Concepts and Forces | 4 | 1 (Seiðr→Masking Seidr) | 0 | 3 |
| Structural Terminology | 2 | 0 | 0 | 2 |
| **Totals** | **66** | **1** | **24** | **41** |

**Assessment:** The vast majority of mythological names referenced in the project portfolio overview lack confirmed technical mappings in the available documentation. This is expected — the README describes the project at a high level, not at the module-signature level. An agent with repository access must systematically traverse the source tree, extract every mythologically-derived identifier, and populate this glossary with verified technical equivalents.

---

## Population Procedure For Inheriting Agents

1. Clone the repository: `git clone https://github.com/hrabanazviking/RuneForgeAI-Project-Aesir.git`
2. Enumerate all source files: `find aesir_engine/ -name "*.mojo" -o -name "*.🔥"`
3. Extract all identifiers (function names, struct names, variable names, module names).
4. Cross-reference each identifier against the mythological terms in this glossary.
5. For each match, trace the implementation to determine the technical function.
6. Update the corresponding entry with the confirmed mapping.
7. Move the entry's status from "Needs Verification" or "Fully Unmapped" to "Confirmed From Source."
8. Update the Confirmation Tracker table.
9. Commit with message: `docs: populate GLOSSARY.md with verified mythological-to-technical mappings`
10. Push the feature branch for review against `main`.

Do not submit unverifiable mappings. An unmapped entry is more valuable than a guessed one.

---

## Etymology Quick Reference

For agents encountering unfamiliar Norse terms not yet in this glossary:

| Root/Stem | Meaning | Likely Technical Association |
|-----------|---------|------------------------------|
| brunnr | well, spring | data source, knowledge store |
| garðr | enclosure, yard | boundary, namespace, scope |
|heimr | world, realm | subsystem, domain, environment |
| höll | hall | aggregation point, registry |
| móti | meeting, confrontation | junction, comparator, diff |
| norrn | knot, twist | entanglement, coupling, dependency |
| rún | secret, whisper | encoded identifier, cipher key |
| stafr | staff, stick | pointer, handle, reference |
| vél | machine, contrivance | engine, apparatus, mechanism |
| völva | seeress | predictor, forecaster, estimator |

Use this table to decompose compound names. For example, "Mímírsvellir" would decompose to "Mímir's well" → "knowledge source belonging to the advisory subsystem."

---

## Amendment Protocol

When adding new entries:

1. Place the entry in the correct mythological section.
2. Use the exact heading format shown above.
3. Fill every field. If a field is genuinely unknown, write "Unknown — not yet traced in source" rather than leaving it blank.
4. Update the Confirmation Tracker.
5. Add the entry to the Etymology Quick Reference if it contains a root not yet listed.
6. Commit with a descriptive message identifying which entries were added or updated.

---

## Final Notes

This glossary is a living document. It is incomplete by design at this stage — it catalogs what the README names and maps the one confirmed correspondence (Seiðr → Masking Seidr). Everything else is a structured hypothesis awaiting source verification.

An inheriting agent who skips the verification step and treats the probable mappings as confirmed will propagate misinformation into the institutional memory. That is a violation of the project's documentation integrity standards.

Verify. Populate. Commit. Push.

---
