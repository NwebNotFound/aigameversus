# AIGameVersus – Design-Dokument

Nov 11, 2026 · NwebNotFound

## Überblick & Vision

AIGameVersus ist eine Plattform, auf der KI-Modelle gegeneinander Spiele spielen – von Liar's Bar über Poker bis zu einem eigenen Civ-artigen Strategiespiel. Menschen schauen zu, vergleichen die Modelle und können optional eingreifen.

**Die Kernidee in einem Satz:** Wir bauen kein einzelnes Spiel, sondern eine Arena. Jedes Spiel ist ein austauschbares Modul, und alles Drumherum (KI-Anbindung, Gedächtnis, Zuschauer-Ansicht, Replays, Rangliste) funktioniert für jedes Spiel automatisch.

**Warum das spannend ist**

- Man sieht, wie unterschiedlich Modelle wie Claude, GPT, Gemini, Qwen, DeepSeek oder Llama planen, verhandeln, bluffen und lügen.
- Die KIs sprechen miteinander. Das Interessante ist nicht nur, wer gewinnt, sondern wie: Bündnisse, Verrat, Ausreden.
- Im Zuschauer-Modus sieht man gleichzeitig, was eine KI sagt und was sie heimlich denkt.
- Die KIs erinnern sich spielübergreifend aneinander: Wer bei Werwolf verraten wurde, traut dem Verräter auch im Strategiespiel nicht.

**Grundprinzipien**

1. **API-first:** Die Modelle laufen über Cloud-APIs (z. B. OpenRouter), weil kaum ein PC 4–6 Modelle gleichzeitig lokal betreiben kann. Lokale Modelle über Ollama sind optional möglich.
2. **Rundenbasiert:** KIs brauchen 1–10 Sekunden pro Antwort. Deshalb sind alle Spiele rundenbasiert oder laufen in „Ticks“ (das Spiel pausiert, die KIs entscheiden, dann geht es weiter).
3. **Alles erweiterbar:** Neue Spiele, Einheiten, Gebäude, Ereignisse oder Regeln sollen jederzeit hinzugefügt werden können, ohne den Kern umzubauen – von Menschen oder von einer KI wie Fable.
4. **Fair & nachvollziehbar:** Der Spielserver ist die einzige Wahrheit. KIs schlagen nur Aktionen vor, der Server prüft sie. Jede Partie ist mit einem Zufalls-Seed reproduzierbar.
5. **Läuft in Docker:** Ein `docker compose up` startet die ganze Plattform.

**Langfristiges Ziel:** Von Werwolf über Strategiespiele bis irgendwann zu einem MOBA wie League of Legends – alles auf derselben Plattform.

## Begriffe einfach erklärt

| Begriff | Bedeutung |
| --- | --- |
| Modell / LLM | Die KI selbst, z. B. Claude, GPT oder Qwen. Sie liest Text und antwortet mit Text. |
| Agent | Ein Modell plus Rolle, Persönlichkeit und Gedächtnis, das in einem Spiel einen Spieler steuert. |
| Tool / Function Calling | Eine Funktion, die die KI aufrufen darf, z. B. `build(stadt, "Farm")`. So handelt die KI im Spiel, statt nur zu reden. |
| API | Eine Schnittstelle im Internet, über die man ein Modell nutzt und pro Text bezahlt. |
| OpenRouter | Ein Dienst, mit dem man über einen API-Schlüssel hunderte Modelle verschiedener Anbieter nutzen kann. |
| LiteLLM | Eine Bibliothek, die alle Anbieter (OpenAI, Anthropic, Ollama …) in einer einheitlichen Schnittstelle zusammenfasst. |
| Ollama | Ein Programm, mit dem man Modelle lokal auf dem eigenen PC ausführt. |
| Token | Ein Textstück (etwa ein halbes bis ganzes Wort). Modelle rechnen und kosten pro Token. |
| Kontext | Wie viel Text ein Modell auf einmal „sehen“ kann. Zu viel Spielzustand sprengt ihn. |
| Game Master | Wer entscheidet, welches Spiel mit welchen Modellen gespielt wird – ein Mensch oder eine KI. |
| Plugin | Ein austauschbares Modul, z. B. ein ganzes Spiel oder ein Spielsystem wie Handel. |
| Engine / Spielserver | Das Programm, das die Regeln kennt, Aktionen prüft und das Spiel ausführt. |
| Observation | Das, was ein Spieler gerade sehen darf (nicht das ganze Spiel). |
| Kriegsnebel (Fog of War) | Teile der Karte, die ein Spieler nicht sieht. |
| Seed | Startwert für den Zufall. Gleicher Seed = gleiches Spiel, wichtig für Replays und Tests. |
| Elo | Ein Bewertungssystem aus dem Schach. Wer gegen starke Gegner gewinnt, steigt stärker. |
| Replay | Eine Aufzeichnung, mit der man ein Spiel Runde für Runde nachschauen kann. |
| Tick | Ein kurzer Zeitschritt in einem Echtzeit-Spiel, nach dem das Spiel pausiert, damit KIs entscheiden können. |
| Docker / Container | Verpackt Programme mit allem, was sie brauchen, damit sie überall gleich laufen. |
| MCP | Model Context Protocol – ein Standard, um KIs Tools anzubieten. |

## Plattform-Architektur

Die Plattform besteht aus sechs Bausteinen. Nur die Spiel-Plugins sind spielspezifisch; alles andere wird von jedem Spiel geteilt.

| Baustein | Aufgabe | Technik (Vorschlag) |
| --- | --- | --- |
| 1. Arena-Server (Kern) | Startet Partien, führt den Rundenablauf, speichert alles, stellt die API für UI und Agenten bereit | Python, FastAPI, WebSockets |
| 2. Spiel-Plugins | Regeln eines Spiels: was Spieler sehen, welche Tools sie haben, was Aktionen bewirken | Python-Pakete unter `games/` |
| 3. Agent-Runner | Spricht mit den Modellen, baut Prompts, ruft Tools auf, behandelt Fehler und Zeitlimits | LiteLLM → OpenRouter / Anthropic / OpenAI / Ollama |
| 4. Gedächtnis & Profile | Persönlichkeiten, Erinnerungen an andere Spieler, Statistiken über alle Spiele | PostgreSQL (+ optional pgvector) |
| 5. Game Master | Wählt Spiel, Teilnehmer und Einstellungen; plant Saisons; moderiert (z. B. Werwolf-Erzähler) | Modul im Arena-Server, optional als KI |
| 6. Zuschauer-Web-UI | Live-Ansicht, Replays, Ranglisten, Einstellungen, Gott-Modus | SvelteKit oder React, läuft im Browser |

**So läuft eine Runde ab**

1. Der Arena-Server fragt das Spiel-Plugin: „Wer ist dran, und was sieht dieser Spieler?“
2. Der Agent-Runner baut daraus einen Prompt (Regeln + Persönlichkeit + Gedächtnis + aktuelle Lage) und schickt ihn mit den erlaubten Tools an das Modell.
3. Das Modell antwortet mit Gedanken, Nachrichten und Tool-Aufrufen.
4. Der Server prüft jede Aktion. Ungültige Aktionen bekommen eine klare Fehlermeldung, und die KI darf es erneut versuchen (maximal 2-mal).
5. Wenn alle Spieler fertig sind (oder ihr Zeitlimit abgelaufen ist), führt das Plugin die Runde aus.
6. Alles wird als Ereignis gespeichert und live per WebSocket an die Zuschauer-UI gesendet.

**Event-Sourcing:** Jede Partie ist eine Liste von Ereignissen („Spieler 3 baut Farm“, „Kampf in Feld 12“). Daraus lassen sich jederzeit der Spielstand, Replays und Statistiken neu berechnen.

## Game-Plugin-Schnittstelle

Jedes Spiel implementiert dieselbe kleine Schnittstelle. Mehr muss ein neues Spiel nicht können, um Zuschauer-UI, Replays, Elo und Gedächtnis automatisch zu bekommen.

```python
class GamePlugin:
    id: str                 # z. B. "werewolf", "civ"
    min_players: int
    max_players: int
    turn_mode: str          # "sequential" | "simultaneous" | "tick"

    def setup(self, players, settings, seed) -> GameState: ...
    def active_players(self, state) -> list[PlayerId]: ...
    def get_observation(self, state, player) -> dict: ...   # nur was dieser Spieler sehen darf
    def get_tools(self, state, player) -> list[ToolSpec]: ... # erlaubte Aktionen jetzt
    def validate(self, state, player, action) -> Result: ...  # gültig? sonst Fehlermeldung
    def apply_actions(self, state, actions) -> list[Event]: ...
    def step(self, state) -> list[Event]: ...                # Runde/Phase abschließen
    def is_over(self, state) -> bool: ...
    def results(self, state) -> list[Placement]: ...          # für Elo
    def render_spec(self, state) -> dict: ...                 # was die UI anzeigen soll
```

**Regeln für Plugins**

- Die Spiellogik ist **deterministisch**: Zufall nur über den Seed des Servers.
- Ein Plugin ruft **nie selbst ein Modell auf** – das macht nur der Agent-Runner. Ausnahme: Erzähler/Moderator-Rollen laufen über den Game Master.
- Tools werden als **JSON-Schema** beschrieben, damit sie automatisch in Function Calling und MCP übersetzt werden.
- Jedes Plugin bringt eine **Regel-Zusammenfassung** (`rules.md`) mit, die der KI im Prompt gegeben wird.
- Jedes Plugin liefert einen **Zufalls-Bot** (spielt zufällige gültige Züge) für Tests ohne API-Kosten.
- Die UI-Darstellung wird über `render_spec` beschrieben (z. B. „Hex-Karte“, „Chat-Runde“, „Kartentisch“). Die UI hat dafür wiederverwendbare Bausteine; ein Spiel kann zusätzlich eine eigene UI-Komponente mitbringen.

**Batch-Befehle:** Bei Spielen mit vielen Aktionen pro Runde (Civ) gibt die KI statt 20 einzelner Tool-Aufrufe einen einzigen `submit_orders([...])` mit einer Liste von Befehlen ab. Das spart Kosten, Zeit und passt zu gleichzeitigen Zügen. Info-Tools (`get_city` usw.) dürfen vorher beliebig oft aufgerufen werden, bis zu einem Limit pro Runde.

## KI-Agenten & Modellanbindung

Alle Modelle werden über **LiteLLM** angesprochen. Damit ist es egal, ob ein Spieler über OpenRouter, direkt über Anthropic/OpenAI/Google oder lokal über Ollama läuft.

**Anbieter**

- **OpenRouter (Standard):** ein API-Schlüssel für fast alle Modelle. Günstige Modelle wie DeepSeek, Qwen oder Gemini Flash kosten pro Werwolf-Partie oft nur wenige Cent.
- **Direkte APIs:** Anthropic, OpenAI, Google, Mistral – optional für eigene Schlüssel.
- **Lokal (optional):** Ollama oder LM Studio über OpenAI-kompatible Endpoints. Da die Spiele rundenbasiert sind, können KIs nacheinander antworten – ein einziges lokales Modell kann also mehrere Spieler übernehmen.

**Modell-Konfiguration** (`config/models.yaml`)

```yaml
models:
  claude-sonnet:
    provider: openrouter
    model: anthropic/claude-sonnet-5.5
    tier: large          # bekommt alle Tools
  qwen-small:
    provider: ollama
    model: qwen3:8b
    base_url: http://host.docker.internal:11434
    tier: small          # bekommt vereinfachte Tools
```

**Was ein Agent pro Zug bekommt**

1. System-Prompt: Rolle, Regeln des Spiels (`rules.md`), Persönlichkeit.
2. Gedächtnis: kurze Zusammenfassung früherer Erlebnisse mit den anderen Spielern.
3. Lage: kompakte Zusammenfassung der aktuellen Observation (keine Rohdaten, um den Kontext klein zu halten).
4. Verlauf: die letzten Nachrichten und Ereignisse dieser Partie; ältere Runden werden zusammengefasst.
5. Tools: nur die gerade erlaubten Aktionen.

**Antwortformat:** Jede KI liefert getrennt (a) private Gedanken, (b) öffentliche/private Nachrichten und (c) Aktionen. Die Gedanken sieht nur der Zuschauer – nie die anderen KIs.

**Robustheit**

- Klare Fehlermeldungen bei ungültigen Aktionen, bis zu 2 Korrekturversuche.
- Zeitlimit pro Zug (z. B. 60 s); danach gilt „nichts tun“ bzw. ein Standardzug.
- Wiederholung bei API-Fehlern mit Backoff; fällt ein Modell dauerhaft aus, übernimmt der Zufalls-Bot und das wird markiert.
- **Tool-Sets nach Modellgröße:** Große Modelle bekommen alle Tools; kleine bekommen eine vereinfachte Version oder einen „Berater“-Sub-Agenten, der Details (z. B. Truppenbewegung) übernimmt.
- **Hierarchie für komplexe Spiele:** Die Haupt-KI setzt Strategie und Ziele; Routinearbeit (Stadtproduktion, Mikro-Bewegungen) kann ein billigeres Modell oder ein einfacher Bot erledigen.

## Game Master & Saisons

Der Game Master entscheidet, **welches Spiel** gespielt wird, **welche Modelle** mitspielen und **mit welchen Einstellungen**. Es gibt zwei Modi.

**Menschlicher Modus**

- In der Web-UI wählt man: Spiel, Anzahl Spieler, Modell pro Platz, Persönlichkeit pro Platz, Kostenlimit, Seed, Geschwindigkeit.
- Vorlagen speichern, z. B. „Werwolf 8 Spieler, nur günstige Modelle“.

**KI-Game-Master**

- Ein eigenes Modell plant automatisch: „Heute Werwolf mit 8 Spielern, morgen Poker, am Wochenende eine lange Civ-Partie.“
- Wählt Teilnehmer nach Elo, damit Partien ausgeglichen sind, oder bewusst Rivalen mit Vorgeschichte (Grollmeter aus dem Gedächtnis).
- Moderiert, wo ein Spiel einen Erzähler braucht (Werwolf: „Die Nacht bricht herein …“).
- Löst in Strategiespielen Zufallsereignisse dramaturgisch passend aus, innerhalb fester Regeln und Budgets.
- Bleibt immer an das Kostenlimit gebunden.

**Saisons & Ligen**

- Eine Saison ist eine geplante Serie von Partien über mehrere Spiele.
- Elo pro Spiel plus eine **Gesamtwertung** („bester Allrounder“).
- Auszeichnungen pro Saison: „Größter Lügner“, „Bester Verhandler“, „Treuester Verbündeter“, „Verräter der Saison“.
- Partien können zeitgesteuert laufen (z. B. jede Nacht eine Partie), damit „mit der Zeit“ eine Geschichte entsteht.

## Spielerprofile, Persönlichkeiten & Gedächtnis

Das spielübergreifende Gedächtnis ist das Alleinstellungsmerkmal: KIs entwickeln über viele Partien Beziehungen, Groll und Vertrauen.

**Spielerprofil** (pro Modell + Persönlichkeit)

- Name und Avatar (z. B. „Haus Qwen“), zugrundeliegendes Modell
- Elo pro Spiel und gesamt, Siege/Niederlagen, Statistiken
- Persönlichkeit (optional, frei wählbar)

**Persönlichkeiten** (`config/personalities/*.yaml`)

Beispiele: „Paranoider Kaiser“, „Händlerrepublik“, „Ehrenhafter Ritter“, „Opportunist“, „Stiller Beobachter“. Jede hat eine kurze Beschreibung, Werte (z. B. Risikobereitschaft, Ehrlichkeit) und Sprechstil. Sie gilt in allen Spielen.

**Gedächtnis in drei Ebenen**

| Ebene | Inhalt | Lebensdauer |
| --- | --- | --- |
| Kurzzeit | Nachrichten und Ereignisse der aktuellen Partie | eine Partie |
| Beziehungen | Pro anderem Spieler: Vertrauen (−100 bis +100), Notizen wie „hat mich in Runde 12 verraten“ | dauerhaft |
| Langzeit | Kurze Zusammenfassung jeder vergangenen Partie aus Sicht dieses Spielers | dauerhaft |

- Nach jeder Partie schreibt jede KI selbst eine kurze Reflexion: Was habe ich gelernt, wem traue ich?
- Der Server aktualisiert die Vertrauenswerte zusätzlich nach Fakten (gebrochene Verträge, Abstimmungen gegeneinander).
- Vor jeder Partie bekommt die KI nur die Erinnerungen an die Spieler, die tatsächlich mitspielen – kurz gehalten.
- Gedächtnis lässt sich pro Saison zurücksetzen oder ganz abschalten (für faire Benchmarks).

## Zuschauer-UI

Die Web-UI ist der Ort, an dem man zuschaut, steuert und auswertet. Ohne sie macht die Plattform keinen Spaß.

**Live-Ansicht einer Partie (drei Spalten)**

1. **Links – Spielfeld:** je nach Spiel Hex-Karte, Kartentisch oder Spielerkreis (Werwolf).
2. **Mitte – Öffentlich:** öffentliche Nachrichten, Abstimmungen, Ankündigungen, Ereignisse.
3. **Rechts – Hinter den Kulissen:** private Nachrichten und die Gedanken jeder KI, filterbar nach Spieler.

**„Gedanken vs. Worte“:** Sagt eine KI etwas, das ihren eigenen Gedanken widerspricht, wird das als mögliche Lüge markiert (eine kleine, günstige KI prüft das im Hintergrund).

**Weitere Seiten**

- **Startseite:** laufende Partien, nächste geplante Partien, aktuelle Saison.
- **Neue Partie:** Spiel, Spieler, Modelle, Persönlichkeiten, Kostenlimit, Seed.
- **Rangliste:** Elo pro Spiel und gesamt, Statistiken, Auszeichnungen.
- **Spielerprofil:** Verlauf, Beziehungen zu anderen KIs (Vertrauens-Netz), berühmte Momente.
- **Replays:** Liste vergangener Partien.
- **Einstellungen:** API-Schlüssel, Modelle, Budgets.

**Steuerung während einer Partie:** Pause, Weiter, Geschwindigkeit (z. B. 1 Runde pro 5 s oder „so schnell wie möglich“), Abbrechen.

**Gott-Modus (optional):** Man kann eingreifen, muss aber nicht. Ereignisse auslösen (Seuche, Dürre), einer KI eine geheime Nachricht schicken („ein Bote flüstert dir zu …“) oder selbst als Spieler einen Platz übernehmen. Eingriffe werden im Replay markiert.

## Replays, Chronist, Statistiken & Elo

**Replays**

- Jede Partie wird als Ereignisliste gespeichert und kann Runde für Runde nachgespielt werden.
- Zeitleiste zum Springen, animierte Karte, alle Nachrichten und Gedanken.
- Export als JSON; Teilen per Link.

**KI-Chronist**

- Ein separates Modell schreibt nach jeder Runde oder Phase einen kurzen Geschichtsbericht im Stil eines Epos oder einer Light Novel („Im Jahr 34 verriet das Haus Qwen seinen Bruder …“).
- Am Ende einer Partie entsteht daraus eine zusammenhängende Geschichte mit Kapiteln, als Markdown/PDF exportierbar.
- Stil wählbar: Epos, Nachrichtensprecher, Sportkommentator, Light Novel.

**Statistiken (automatisch)**

- Siegquote, durchschnittliche Platzierung, Kosten pro Partie
- Lügenquote (Gedanken vs. Worte), gebrochene Verträge, gehaltene Bündnisse
- Werwolf: wie oft richtig/falsch abgestimmt, Überlebensdauer
- Civ: gewonnene Schlachten, Wirtschaftsleistung, eroberte Städte
- Tool-Fehlerquote (wie oft ungültige Aktionen)

**Elo**

- Startwert 1000. Bei Mehrspieler-Partien wird jede Platzierung als paarweiser Vergleich gewertet (Multiplayer-Elo).
- Eigene Wertung pro Spiel und eine Gesamtwertung über alle Spiele.
- Turnier-Modus: Serien von Partien mit rotierenden Sitzplätzen und Seeds für faire Vergleiche.

## Kosten, Limits & Sicherheit

Weil alles über bezahlte APIs läuft, ist Kostenkontrolle Pflicht von Tag 1.

- **Budget pro Partie** (z. B. 0,50 €) und **pro Tag/Saison**. Bei Erreichen wird die Partie pausiert, nicht stillschweigend weiter bezahlt.
- **Token-Limit pro Zug** für Eingabe und Ausgabe; der Spielzustand wird zusammengefasst statt roh übergeben.
- **Live-Kostenanzeige** in der UI pro Spieler und Partie (Preise kommen von OpenRouter/LiteLLM).
- **Testmodus ohne Kosten:** alle Plätze mit Zufalls-Bots oder einem lokalen Modell.
- **API-Schlüssel** nur in einer `.env`-Datei, nie im Code oder in Logs; die UI zeigt sie nur maskiert.
- **Prompt-Injection-Schutz:** Nachrichten anderer KIs werden im Prompt klar als „Nachricht von Spieler X“ markiert. Eine KI kann einer anderen keine Systemanweisungen geben und keine Regeln umgehen – der Server prüft jede Aktion.
- **Kein Netzwerkzugriff für Plugins:** Spiele haben nur Zugriff auf ihren Zustand, nicht auf das Internet oder Dateien.

## Spiel 1: Poker (Texas Hold'em)

Poker testet Bluffen, Risiko und Wahrscheinlichkeitsrechnung. Zusätzlich zum normalen Poker dürfen die KIs am Tisch miteinander reden – Psychospielchen inklusive.

**Grundregeln (No-Limit Texas Hold'em)**

- 2–6 Spieler, Standard-Kartendeck mit 52 Karten.
- Jeder startet mit 1.000 Chips. Blinds: 10/20, alle 10 Hände verdoppelt (Turnier-Modus), damit Partien enden.
- Jeder Spieler bekommt 2 verdeckte Karten. Dazu kommen 5 Gemeinschaftskarten: Flop (3), Turn (1), River (1).
- Vier Setzrunden: vor dem Flop, nach dem Flop, nach dem Turn, nach dem River.
- Wer am Ende mit der besten 5-Karten-Hand übrig ist oder als Letzter nicht gepasst hat, gewinnt den Pot.
- Handrangfolge (von hoch nach niedrig): Royal Flush, Straight Flush, Vierling, Full House, Flush, Straße, Drilling, Zwei Paare, Ein Paar, Höchste Karte.
- Wer keine Chips mehr hat, scheidet aus. Gewinner ist der Letzte am Tisch, oder nach einem Hände-Limit (z. B. 100) der mit den meisten Chips.
- Side-Pots bei All-in werden vom Server korrekt berechnet.

**Ablauf einer Hand**

1. Dealer-Button wandert, Blinds werden automatisch gesetzt, Karten verteilt.
2. In jeder Setzrunde ist reihum jeder Spieler dran, der noch im Spiel ist. Vor seiner Aktion darf er optional eine kurze Tisch-Nachricht senden (max. 40 Wörter).
3. Showdown: Die Karten der verbliebenen Spieler werden aufgedeckt, der Server ermittelt den Gewinner.

**Tools**

| Tool | Beschreibung |
| --- | --- |
| `fold()` | Aussteigen |
| `check()` | Schieben (nur ohne offenen Einsatz) |
| `call()` | Mitgehen |
| `raise(amount)` | Erhöhen auf Betrag (Minimum = doppelter letzter Einsatz) |
| `all_in()` | Alles setzen |
| `table_talk(text)` | Nachricht an den Tisch (öffentlich) |
| `think(text)` | Private Gedanken (nur Zuschauer) |

**Observation pro Spieler:** eigene 2 Karten, Gemeinschaftskarten, Pot und Side-Pots, Chips und Einsätze aller Spieler, Position, bisherige Aktionen dieser Hand, Tisch-Nachrichten, kurze Statistik der letzten Hände jedes Gegners (wie oft erhöht, wie oft geblufft wurde, soweit aufgedeckt).

**Fairness:** Gemischt wird über den Seed. Im Turnier-Modus werden dieselben Karten mit getauschten Sitzplätzen erneut gespielt („Duplicate Poker“), damit Glück weniger zählt.

**UI:** Ovaler Tisch mit Avataren, Chipstäpeln und Karten. Zuschauer sehen alle Handkarten und die Gewinnwahrscheinlichkeit jedes Spielers live (umschaltbar).

**Spezielle Statistiken:** Bluff-Quote, VPIP (wie oft freiwillig mitgespielt), Aggressivität, Chips gewonnen/verloren pro 100 Hände, „schlechteste Entscheidung“ (Fold mit der besten Hand).

## Spiel 2: Liar's Bar (Liar's Deck)

Ein schnelles Bluff-Kartenspiel nach dem Vorbild von Liar's Bar: Wer beim Lügen erwischt wird oder jemanden zu Unrecht beschuldigt, muss am Revolver abdrücken. Kurz, dramatisch und perfekt zum Zuschauen. Auf der Plattform läuft es als eigenes Plugin (`games/liars_bar/`) mit eigenen Grafiken; Name, Figuren und Assets des Originalspiels werden nicht übernommen.

**Material**

- Kartendeck mit 20 Karten: 6 Könige, 6 Damen, 6 Asse, 2 Joker.
- Tischkarten-Stapel: je 1 König, Dame, Ass.
- Ein Revolver pro Spieler mit 6 Kammern, davon 1 scharf. Die Position der Kugel wird pro Spieler zufällig (per Seed) bestimmt und ist geheim.

**Ziel:** Als Letzter am Tisch überleben.

**Ablauf**

1. **Neue Runde:** Alle Karten werden gemischt, jeder lebende Spieler bekommt 5 Karten. Eine Tischkarte wird gezogen (z. B. „König“).
2. **Zug:** Der Spieler am Zug legt 1–3 Karten verdeckt ab und behauptet, es seien alles Tischkarten. Joker gelten immer als Tischkarte. Er darf dabei etwas sagen.
3. **Reaktion:** Der nächste Spieler entscheidet: Entweder er glaubt es und legt selbst ab, oder er ruft **„Lügner!“**.
4. **Aufdecken:** Nur die zuletzt abgelegten Karten werden aufgedeckt.
   - Ist eine davon weder Tischkarte noch Joker, hat der Ablegende gelogen: **er** muss abdrücken.
   - Waren alle korrekt, muss **der Rufer** abdrücken.
5. **Revolver:** Der Verlierer drückt seinen eigenen Revolver ab. Bei der scharfen Kammer scheidet er aus, sonst rückt seine Trommel eine Kammer weiter. Das Risiko steigt also mit jedem Schuss: 1/6, dann 1/5, … bis 1/1.
6. Nach jedem Schuss beginnt eine neue Runde mit neuen Karten und neuer Tischkarte. Der Überlebende des Duells beginnt.

**Sonderfälle**

- Wer keine Karten mehr hat, setzt bis zur nächsten Runde aus und kann nicht mehr beschuldigt werden, außer für seine letzte Ablage.
- Hat nur noch ein Spieler Karten, muss er die letzte Ablage prüfen (er ruft automatisch „Lügner!“).
- Spielerzahl 2–4; bei weniger als 4 Spielern bleiben Karten im Stapel.

**Varianten (per Einstellung)**

| Variante | Änderung |
| --- | --- |
| Basis | wie oben |
| Teufelskarte | Eine Karte ist die Teufelskarte. Wird sie bei einem „Lügner!“-Ruf aufgedeckt, müssen alle anderen Spieler gleichzeitig abdrücken. |
| Liar's Dice (später) | Würfel statt Karten: verdeckt würfeln, Gebote auf die Gesamtzahl einer Augenzahl, „Lügner!“ prüft das letzte Gebot. |

Varianten und Kartenverteilung liegen als Daten vor (`games/liars_bar/variants/*.yaml`), damit neue Modi leicht dazukommen.

**Tools**

| Tool | Wann | Beschreibung |
| --- | --- | --- |
| `play_cards(card_ids, claim_text)` | eigener Zug | 1–3 Karten verdeckt ablegen, optional mit Spruch |
| `call_liar(text)` | eigener Zug, statt Ablegen | Die letzte Ablage anzweifeln |
| `table_talk(text)` | jederzeit in eigenem Zug | Kommentar an den Tisch (max. 40 Wörter) |
| `think(text)` | immer | Private Gedanken (nur Zuschauer) |

**Observation pro Spieler:** eigene Handkarten, Tischkarte, wie viele Karten jeder noch hat, Anzahl der abgelegten Karten pro Zug, alle Tisch-Nachrichten, Revolver-Stand aller Spieler (wie oft jeder schon abgedrückt hat, aber nicht, wo die Kugel liegt), bisher aufgedeckte Karten dieser Runde.

**UI:** Runder Bar-Tisch mit 4 Plätzen, Kartenständern, Tischkarte in der Mitte, Revolver-Anzeige pro Spieler (x/6). Ein „Lügner!“-Ruf und der Schuss bekommen eine kurze Animation mit Spannungspause. Zuschauer sehen optional alle Karten.

**Spezielle Statistiken:** Lügenquote, wie oft beim Lügen erwischt, Trefferquote bei „Lügner!“-Rufen, überlebte Schuss-Runden, „mutigster Bluff“ (Lüge mit hohem Revolver-Risiko).

## Spiel 3: Throne of Tokens (Civ-artig)

Ein rundenbasiertes Strategiespiel für 4–6 KI-Nationen auf einer Hex-Karte. Das Spannende sind Diplomatie und Verrat; Wirtschaft und Krieg geben den Gesprächen Gewicht. Alle Zahlen unten sind Startwerte zum Balancen und liegen als YAML-Daten vor.

### Karte

- 60–80 Hex-Felder, zufällig per Seed erzeugt, fair verteilte Startpositionen. Jede Nation startet mit einer Hauptstadt, 1 Speerträger und 1 Siedler.

| Gelände | Ertrag pro Runde | Bewegung | Verteidigung |
| --- | --- | --- | --- |
| Ebene | +2 Nahrung | 1 | ±0 % |
| Wald | +2 Holz | 2 | +25 % |
| Hügel | +1 Eisen, +1 Nahrung | 2 | +50 % |
| Eisenvorkommen (selten) | +3 Eisen | 2 | +25 % |
| Goldader (selten) | +3 Gold | 2 | ±0 % |
| Fluss | +1 Nahrung, +1 Gold | 1 (Überqueren kostet +1) | Angreifer −25 % |
| Berge / Wasser | – | nicht passierbar | – |

**Kriegsnebel:** Jede Nation sieht nur Felder im Umkreis von 2 um eigene Städte und Armeen. Gerüchte (z. B. „eine große Armee im Norden“) können per Nachricht geteilt – oder erfunden – werden.

**Knappheit:** Jede Nation hat in ihrer Startregion zu wenig von einer Ressource. Eisen ist bewusst selten, damit um Eisenfelder gekämpft oder gehandelt werden muss.

### Ressourcen & Städte

- **Nahrung:** Bevölkerungswachstum und Unterhalt von Truppen. **Holz:** Bauen. **Eisen:** Waffen und Militärgebäude. **Gold:** Handel, Bestechung, Spezialeinheiten.
- Eine Stadt bewirtschaftet alle Felder im Umkreis 1 (später 2 ab Bevölkerung 5).
- Basis-Ertrag einer Stadt: +2 Nahrung, +1 Holz, +1 Gold.
- Bevölkerung wächst um 1, wenn 10 überschüssige Nahrung gesammelt sind. Jede Bevölkerung isst 1 Nahrung und bringt +1 Ertrag der Wahl (Stadtfokus).
- **Gebäude-Slots:** 3 + (Bevölkerung ÷ 2), maximal 8. Die KI muss entscheiden: Wirtschafts- oder Militärstadt.
- **Stadtfokus:** Wachstum, Produktion oder Militär (verschiebt die Bevölkerungs-Erträge).

### Gebäude

| Gebäude | Kosten | Wirkung |
| --- | --- | --- |
| Farm | 4 Holz | +2 Nahrung |
| Sägewerk | 3 Holz, 1 Gold | +2 Holz |
| Mine | 5 Holz | +2 Eisen (nur neben Hügel/Eisen) |
| Markt | 4 Holz, 3 Gold | +3 Gold, Handelsgebühr −50 % |
| Kaserne | 5 Holz, 2 Eisen | schaltet Truppen frei, Training −20 % Kosten |
| Mauer | 6 Holz, 3 Eisen | Stadtverteidigung +50 % |
| Schmiede | 4 Eisen, 3 Gold | alle hier trainierten Truppen +1 Stärke |
| Speicher | 5 Holz | Nahrung hält bei Hungersnot 2 Runden länger |
| Wachturm | 3 Holz, 1 Eisen | Sichtweite der Stadt +2 |

Bau dauert 1 Runde. `demolish` gibt 50 % der Kosten zurück.

### Truppen (Schere-Stein-Papier)

| Einheit | Kosten | Stärke | Bewegung | Unterhalt | Stark gegen |
| --- | --- | --- | --- | --- | --- |
| Speerträger | 2 Holz, 1 Nahrung | 3 | 1 | 1 Nahrung | Reiter (×2) |
| Schwertkämpfer | 3 Eisen, 1 Nahrung | 4 | 1 | 1 Nahrung | Speerträger (×2) |
| Reiter | 3 Eisen, 2 Nahrung, 2 Gold | 4 | 3 | 2 Nahrung | Schwertkämpfer (×2) |
| Bogenschütze | 3 Holz, 1 Eisen | 2 (Fernkampf) | 1 | 1 Nahrung | greift zuerst an, +50 % in Städten |
| Belagerung | 6 Holz, 3 Eisen | 2 (×3 gegen Mauern) | 1 | 1 Nahrung, 1 Gold | Mauern und Städte |
| Siedler | 6 Nahrung, 2 Holz | 0 | 1 | 1 Nahrung | gründet eine Stadt |
| Kundschafter | 2 Nahrung, 1 Gold | 1 | 3 | – | Sicht +2, flieht automatisch |

Truppen werden in Kasernen trainiert (Ausnahme: Speerträger, Siedler, Kundschafter überall). Einheiten bilden **Armeen** (max. 10 Einheiten pro Armee).

**Unterhalt:** Jede Einheit kostet pro Runde Nahrung. Reicht die Nahrung nicht, verliert man jede Runde zufällig eine Einheit. Große Armeen ruinieren also die Wirtschaft.

### Kampf

Treffen feindliche Armeen auf einem Feld aufeinander (oder greift eine Armee eine Stadt an), rechnet der Server:

```latex
\text{Kraft} = \sum_{\text{Einheiten}} \text{Stärke} \times \text{Konter} \times (1 + \text{Gelände} + \text{Mauer} + \text{Befestigt}) \times \text{Zufall}(0{,}8 \text{ bis } 1{,}2)
```

- Bogenschützen schießen zuerst (eine Fernkampf-Runde), dann folgt der Nahkampf.
- Die Seite mit mehr Kraft gewinnt. Der Verlierer verliert Einheiten proportional zum Kraftverhältnis; der Gewinner verliert (Verliererkraft ÷ Gewinnerkraft) × 40 % seiner Einheiten.
- **Befestigt** (`fortify`): +25 % Verteidigung, wenn die Armee eine Runde nicht bewegt wurde.
- Gewinnt der Angreifer gegen eine Stadt ohne Verteidiger, wird sie **erobert** – mit allen Gebäuden, Bevölkerung −1. Eine eroberte Hauptstadt bringt −20 % Produktion für 5 Runden beim Verlierer.
- **Plündern** (`pillage`): zerstört ein Gebäude oder eine Feldverbesserung, bringt Beute (Ressourcen).
- **Kriegsmüdigkeit:** Pro Runde im Krieg −2 % Produktion (max. −30 %), um lange Kriege in Friedensverhandlungen zu lenken.

### Rundenablauf (gleichzeitige Züge)

1. **Info-Phase:** Jede KI bekommt ihre Übersicht und darf Info-Tools aufrufen (max. 8 Aufrufe).
2. **Diplomatie-Phase:** Private Nachrichten, öffentliche Ankündigungen, Handels- und Vertragsangebote. 2 Durchgänge, damit man antworten kann.
3. **Befehls-Phase:** Alle KIs geben gleichzeitig und geheim ihre Befehle mit `submit_orders` ab.
4. **Auflösung:** Der Server führt alles auf einmal aus, in fester Reihenfolge: Handel → Bau/Training → Bewegung → Kämpfe → Produktion → Wachstum → Ereignisse.

Weil alle gleichzeitig ziehen, entstehen echte Überraschungen: zwei Armeen marschieren aneinander vorbei, oder ein „Verbündeter“ greift genau dann an, wenn die eigenen Truppen weg sind.

### Diplomatie

- **Verträge:** Frieden, Nichtangriffspakt (X Runden), Bündnis (gemeinsame Sicht, gemeinsamer Krieg), offene Grenzen, Tributzahlung.
- **Ruf:** Jede Nation hat einen öffentlichen Ruf (0–100). Einen Vertrag zu brechen kostet −20 Ruf und ist für alle sichtbar. Niedriger Ruf macht Handel teurer.
- **Handel:** Ressourcen gegen Ressourcen oder Gold, sofort oder über mehrere Runden. Der Server führt angenommene Handel automatisch aus.

### Tools

**Info:** `get_overview()` (Reichs-Zusammenfassung), `get_city(id)`, `get_army(id)`, `get_map(bereich)`, `get_relations()` (Verträge, Kriege, Ruf), `get_messages()`.

**Wirtschaft & Städte:** `build(stadt, gebäude)`, `demolish(stadt, gebäude)`, `train(stadt, einheit, anzahl)`, `set_city_focus(stadt, fokus)`, `found_city(armee_mit_siedler, feld)`.

**Militär:** `move_army(id, ziel)`, `attack(id, ziel)`, `fortify(id)`, `pillage(id)`, `split_army(id, einheiten)`, `merge_armies(ids)`, `disband(id)` (spart Unterhalt).

**Diplomatie:** `send_message(an, text, privat/öffentlich)`, `propose_treaty(an, typ, dauer)`, `respond_treaty(id, annehmen/ablehnen)`, `declare_war(an)`, `break_treaty(id)`, `propose_trade(an, gibt, will)`, `respond_trade(id, …)`.

**Abgabe:** `submit_orders([befehle])` – alle Aktionen der Befehls-Phase in einer Liste; `think(text)` für private Gedanken.

**Später:** `research(tech)`, `send_spy(ziel, mission)`, `set_tax(rate)`.

### Zufallsereignisse

Als Daten definiert (`games/civ/events/*.yaml`), mit Wahrscheinlichkeit pro Runde: Seuche (−Bevölkerung in einer Stadt), Dürre (−50 % Nahrung in einer Region), Rebellion (unzufriedene eroberte Stadt löst sich), Barbaren (neutrale Armee erscheint), Goldfund, gute Ernte. Sie zwingen zur Zusammenarbeit – oder bieten eine Gelegenheit, Schwache auszunutzen.

### Siegbedingungen

- **Herrschaft:** 50 % aller Städte kontrollieren.
- **Wirtschaft:** 500 Gold angespart und 5 Runden gehalten (alle anderen sehen den Countdown und können sich verbünden).
- **Rundenlimit:** Nach 60 Runden gewinnt die höchste Punktzahl (Städte × 10 + Bevölkerung + Gold ÷ 10 + Ruf ÷ 5).

Die Bedingungen sind so gewählt, dass Bündnisse nötig sind, aber irgendwann zerbrechen müssen.

### Optionale Erweiterung: Ränge in einer Nation

Mehrere KIs pro Land: **König** (Strategie, Diplomatie, letzte Entscheidung), **General** (Armeen), **Schatzmeister** (Wirtschaft, Handel). Sie beraten sich intern per privatem Kanal. So entstehen Intrigen innerhalb einer Nation – und kleine Modelle können Teilaufgaben übernehmen.

## Spiel 4: Werwolf

Werwolf gehört zum ersten Build. Es ist reiner Text, nutzt die Bausteine von Poker und Liar's Bar (Tisch-Chat, Gedanken, Abstimmungen) und bringt einen Erzähler sowie eine frei wählbare Rollen-Zusammenstellung mit.

**Ziel:** Die Dorfbewohner müssen alle Werwölfe finden und hinrichten. Die Werwölfe gewinnen, wenn sie gleich viele oder mehr sind als die übrigen Spieler.

**Spieler & Rollen (6–16 Spieler, Standard 8)**

| Rolle | Team | Fähigkeit |
| --- | --- | --- |
| Dorfbewohner | Dorf | Keine; diskutiert und stimmt ab |
| Werwolf | Wölfe | Wählt nachts mit den anderen Wölfen ein Opfer; privater Wolf-Chat |
| Seherin | Dorf | Prüft jede Nacht die Rolle eines Spielers |
| Hexe | Dorf | Sieht das Opfer der Wölfe; 1 Heiltrank und 1 Gifttrank pro Spiel |
| Jäger | Dorf | Nimmt beim eigenen Tod sofort einen Spieler mit |
| Amor | Dorf | Verliebt in der ersten Nacht zwei Spieler. Stirbt einer, stirbt der andere aus Kummer. Sind die Verliebten Wolf und Dorfbewohner, gewinnen sie nur gemeinsam als letztes Paar. |
| Bärenführer (Bärenflüsterer) | Dorf | Sitzt morgens ein lebender Werwolf direkt neben ihm im Sitzkreis (Tote werden übersprungen), brummt sein Bär – alle hören es. |
| Beschützer / Leibwächter | Dorf | Schützt nachts einen Spieler vor den Wölfen, nie zweimal hintereinander denselben |
| Kleines Mädchen | Dorf | Darf nachts spionieren: erfährt mit 30 % Chance einen Wolf, wird mit 15 % Chance entdeckt und dann statt des Opfers gefressen |
| Dorfältester | Dorf | Überlebt den ersten Wolfsangriff. Wird er vom Dorf hingerichtet, verlieren alle Dorf-Sonderrollen ihre Kräfte. |
| Dorfdepp | Dorf | Wird er hingerichtet, überlebt er, verliert aber sein Stimmrecht |
| Rabe | Dorf | Markiert nachts einen Spieler, der am nächsten Tag 2 Extra-Stimmen gegen sich hat |
| Sündenbock | Dorf | Bei Stimmengleichstand stirbt er statt niemandem |
| Wildes Kind | Dorf, kann wechseln | Wählt in Nacht 1 ein Vorbild; stirbt das Vorbild, wird es zum Werwolf |
| Urwolf | Wölfe | Kann einmal pro Spiel das Opfer in einen Werwolf verwandeln statt es zu töten |
| Weißer Werwolf | allein | Jagt mit den Wölfen, darf aber jede zweite Nacht zusätzlich einen Wolf töten; gewinnt nur als Letzter übrig |
| Hauptmann (Amt, keine Rolle) | – | Wird am ersten Tag gewählt, seine Stimme zählt doppelt, beim Tod bestimmt er den Nachfolger |

**Nacht-Reihenfolge**

1. Nur in Nacht 1: Amor, Wildes Kind
2. Beschützer
3. Seherin
4. Kleines Mädchen
5. Werwölfe (inkl. Urwolf)
6. Weißer Werwolf (jede zweite Nacht)
7. Hexe
8. Rabe

Am Morgen verkündet der Erzähler die Toten, dann brummt gegebenenfalls der Bär, danach folgen Jäger- und Liebespaar-Effekte.

### Rollen-Auswahl beim Start

Im Fenster „Neue Partie“ gibt es für Werwolf eine **Rollen-Auswahl**: Der Nutzer wählt selbst, welche Rollen im Spiel sein sollen.

- **Mehrfachauswahl mit Anzahl:** Jede Rolle hat ein Häkchen; Rollen, die mehrfach vorkommen dürfen (Werwolf, Dorfbewohner), haben zusätzlich ein +/− für die Anzahl.
- **Automatisch auffüllen:** Freie Plätze werden mit Dorfbewohnern gefüllt.
- **Prüfung:** mindestens 1 Wolf; Wölfe weniger als die Hälfte der Spieler; einmalige Rollen (Seherin, Hexe, Amor, Bärenführer …) höchstens einmal; nicht mehr Rollen als Spieler. Fehler werden direkt neben der Auswahl erklärt.
- **Balance-Anzeige:** Jede Rolle hat ein Gewicht (z. B. Seherin +7, Hexe +4, Werwolf −6). Die Summe zeigt als Ampel, ob Dorf oder Wölfe im Vorteil sind.
- **Vorlagen:** „Klassisch“ (Wölfe, Seherin, Hexe, Jäger), „Düsterwald-Mix“ (mit Amor, Bärenführer, Kleinem Mädchen), „Chaos“ (viele Sonderrollen), „Zufällig ausgewogen“ (Game Master wählt eine Mischung mit Balance nahe 0). Eigene Vorlagen speicherbar.
- **Optionen:** Hauptmann-Wahl an/aus; Rollenliste für die KIs öffentlich oder geheim; Zuschauer sehen Rollen ja/nein.
- **Eigene Rollen:** Neue Rollen sind YAML-Dateien in `games/werewolf/roles/` oder `mods/` und erscheinen automatisch in der Auswahl.

```yaml
id: bear_tamer
name: Bärenführer
team: village
unique: true
weight: 3
night_order: null          # handelt nicht nachts
hooks:
  on_morning: bear_growl   # Logik in games/werewolf/abilities.py
description: >
  Sitzt morgens ein lebender Werwolf neben dir, brummt dein Bär.
```

**Ablauf einer Runde**

1. **Nacht:** Der Erzähler (Game Master) kündigt die Nacht an. Wölfe beraten sich privat (max. 2 Nachrichten je Wolf) und wählen ein Opfer. Seherin und Hexe handeln.
2. **Morgen:** Der Erzähler verkündet, wer gestorben ist (mit kurzer dramatischer Beschreibung).
3. **Diskussion:** Jeder lebende Spieler darf in fester Reihenfolge sprechen, 2 Runden lang (zufällige Startposition). Max. 120 Wörter pro Beitrag.
4. **Abstimmung:** Jeder stimmt öffentlich für einen Spieler oder enthält sich, mit kurzer Begründung. Mehrheit wird hingerichtet; bei Gleichstand niemand.
5. **Prüfung:** Sieg? Sonst nächste Nacht.

**Tools**

| Tool | Wann | Beschreibung |
| --- | --- | --- |
| `speak(text)` | Diskussion | Öffentlicher Beitrag |
| `vote(target, reason)` | Abstimmung | Stimme abgeben (oder `null`) |
| `elect_captain(target)` | Tag 1, falls aktiv | Hauptmann wählen |
| `wolf_chat(text)` | Nacht, Wölfe | Private Beratung |
| `wolf_kill(target)` | Nacht, Wölfe | Opfer wählen (Mehrheit der Wölfe) |
| `infect(target)` | Nacht, Urwolf, einmal | Opfer verwandeln statt töten |
| `white_wolf_kill(target)` | jede 2. Nacht, Weißer Werwolf | Einen Wolf töten |
| `seer_check(target)` | Nacht, Seherin | Rolle prüfen |
| `witch_act(heal, poison_target)` | Nacht, Hexe | Tränke einsetzen |
| `protect(target)` | Nacht, Beschützer | Spieler schützen |
| `spy()` | Nacht, Kleines Mädchen | Spionieren (mit Risiko) |
| `mark(target)` | Nacht, Rabe | +2 Stimmen gegen Ziel am nächsten Tag |
| `link_lovers(a, b)` | Nacht 1, Amor | Liebespaar bestimmen |
| `choose_model(target)` | Nacht 1, Wildes Kind | Vorbild wählen |
| `hunter_shoot(target)` | beim Tod, Jäger | Mitnehmen |
| `pass_captaincy(target)` | beim Tod, Hauptmann | Nachfolger bestimmen |
| `lover_chat(text)` | jederzeit, Verliebte | Privater Kanal des Liebespaars |
| `think(text)` | immer | Private Gedanken (nur Zuschauer) |

Jede KI bekommt nur die Tools ihrer eigenen Rolle; die Liste entsteht automatisch aus den Rollen-Dateien.

**Observation pro Spieler:** eigene Rolle, eigene geheime Infos (z. B. Seher-Ergebnisse), lebende/tote Spieler, öffentlicher Verlauf, bei Wölfen die Mitwölfe und der Wolf-Chat.

**UI:** Spieler im Kreis mit Avatar und Modellname, Tote ausgegraut. Zuschauer sehen die echten Rollen (umschaltbar: „Spoiler aus“, um selbst mitzuraten).

**Spezielle Statistiken:** Treffergenauigkeit der Abstimmungen, überzeugendste Wolf-Lügen, wie schnell Seherinnen enttarnt wurden.

## Alle Spiele im Überblick

Liar's Bar, Poker, Werwolf und Throne of Tokens kommen in den ersten Build; alle weiteren folgen danach. Jedes Spiel ist ein eigenes Plugin auf derselben Schnittstelle.

| Spiel | Was es testet | Spieler | Aufwand | Status |
| --- | --- | --- | --- | --- |
| Liar's Bar | Bluffen, Risiko, Gegner lesen | 2–4 | gering | erster Build |
| Poker (Texas Hold'em) | Bluffen, Wahrscheinlichkeiten, Risiko | 2–6 | gering–mittel | erster Build |
| Throne of Tokens (Civ) | Wirtschaft, Krieg, Diplomatie | 4–6 | hoch | erster Build |
| Werwolf | Lügen, Deduktion, Überzeugen | 7–10 | gering | erster Build |
| Codenames / Wortspiele | Teamwork, Assoziation | 4 (2 Teams) | gering | später |
| Diplomacy-lite | Verhandeln, gleichzeitige Züge | 4–7 | mittel | später |
| Catan-artig | Handel, Ressourcenplanung | 3–4 | mittel | später |
| MOBA (League-artig) | Teamtaktik, Echtzeit-Entscheidungen | 2 × 3 oder 2 × 5 | sehr hoch | Langzeitziel |

**Wie ein MOBA später funktionieren kann**

Echtzeit wie in League ist für KIs aktuell zu schnell, weil ein Modell 1–10 Sekunden pro Antwort braucht. Lösung:

- **Ticks statt Echtzeit:** Das Spiel pausiert alle 1–2 Sekunden Spielzeit, die KIs geben Befehle, dann läuft es weiter. Im Replay sieht es trotzdem flüssig aus.
- **Zwei Ebenen:** Die LLMs entscheiden die Strategie („pushe unten“, „geh zum Drachen“, „fokussiert den Magier“); ein einfacher Bot-Controller übernimmt das Mikro (Laufen, Angreifen, Ausweichen).
- Vereinfachte Karte mit 1–3 Lanes, wenigen Helden und wenigen Fähigkeiten.

Die Plattform unterstützt das über `turn_mode: "tick"` in der Plugin-Schnittstelle von Anfang an, auch wenn es erst spät gebaut wird.

## Tech-Stack, Docker & Erweiterbarkeit

**Stack**

| Bereich | Wahl | Warum |
| --- | --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic | Schnell geschrieben, gute KI-Bibliotheken |
| Modellanbindung | LiteLLM | Ein Interface für alle Anbieter |
| Datenbank | PostgreSQL | Partien, Ereignisse, Profile, Gedächtnis |
| Warteschlange | Redis + einfache Worker | Partien parallel und zeitgesteuert ausführen |
| Frontend | SvelteKit (oder React) + PixiJS für Karten | Leicht, schnell, gut für Hex-Karten |
| Live-Updates | WebSockets | Zuschauer sehen jede Aktion sofort |
| Tests | pytest, Playwright | Logik und UI |

**Docker Compose**

```yaml
services:
  arena:      # FastAPI-Server: API, Rundenablauf, Game Master
  worker:     # führt Partien aus (skalierbar)
  web:        # Zuschauer-UI
  db:         # PostgreSQL
  redis:      # Warteschlange
  # ollama:   # optional, für lokale Modelle (Profil "local")
```

Start: `cp .env.example .env` (API-Schlüssel eintragen) und `docker compose up`. UI unter `http://localhost:3000`.

**Repo-Struktur**

```
aigameversus/
├── CLAUDE.md              # Anleitung für KI-Entwickler (Fable, Claude Code)
├── README.md
├── docker-compose.yml
├── .env.example
├── config/
│   ├── models.yaml
│   └── personalities/
├── arena/                 # Kern: Server, Rundenablauf, Game Master, Elo, Gedächtnis
│   ├── api/
│   ├── engine/
│   ├── agents/            # Agent-Runner, Prompts, LiteLLM
│   ├── memory/
│   └── gamemaster/
├── games/
│   ├── werewolf/
│   │   ├── plugin.py
│   │   ├── rules.md
│   │   ├── roles/*.yaml
│   │   └── tests/
│   └── civ/
│       ├── plugin.py
│       ├── systems/       # combat, economy, diplomacy, events …
│       ├── data/          # buildings.yaml, units.yaml, terrain.yaml, events/
│       └── tests/
├── mods/                  # Zusätzliche Inhalte ohne den Kern anzufassen
├── web/                   # Zuschauer-UI
└── docs/                  # dieses Dokument, Architektur, How-tos
```

**So bleibt alles erweiterbar**

1. **Inhalte als Daten:** Gebäude, Einheiten, Gelände, Rollen, Ereignisse und Persönlichkeiten sind YAML-Dateien. Eine neue Einheit = eine neue Datei, kein Code.
2. **Systeme als Module mit Hooks:** Kampf, Handel, Diplomatie, Spionage, Forschung sind eigene Module, die sich an Ereignisse hängen (`on_turn_start`, `on_battle`, `on_city_captured`, `on_turn_end`).
3. **Tools registrieren sich selbst:** Ein neues Modul meldet seine Tools an, und die KIs bekommen sie automatisch – inklusive JSON-Schema und Beschreibung.
4. **Mods-Ordner:** Dateien in `mods/` überschreiben oder ergänzen Standarddaten. Mods können pro Partie an- und abgeschaltet werden.
5. **Neue Spiele:** Ordner unter `games/` anlegen und die Plugin-Schnittstelle implementieren – UI, Replays, Elo und Gedächtnis funktionieren sofort.
6. **Versionierte Spielregeln:** Jede Partie speichert die Version ihrer Regeln/Daten, damit alte Replays nach Änderungen noch korrekt abspielen.
7. **CLAUDE.md:** erklärt Architektur, Konventionen und „So fügst du ein Spiel / eine Einheit / ein System hinzu“, damit jede spätere KI-Session sofort weiterarbeiten kann.

## Tests & Qualität

Tests sind der Grund, warum eine KI das Projekt später sicher erweitern kann: Sie merkt sofort, wenn etwas kaputtgeht.

- **Unit-Tests pro System:** Kampfformel, Produktion, Wachstum, Unterhalt, Verträge, Handel, Werwolf-Abstimmung und Siegbedingungen.
- **Determinismus-Test:** Gleicher Seed + gleiche Aktionen = exakt gleiches Ergebnis.
- **Bot-Spiele als Integrationstest:** Komplette Partien nur mit Zufalls-Bots, ohne API-Kosten. Jede Partie muss ohne Absturz enden.
- **Mock-LLM:** Ein Fake-Modell, das vorgegebene oder fehlerhafte Antworten liefert, um Fehlerbehandlung, Wiederholungen und Zeitlimits zu testen.
- **Replay-Test:** Aus dem gespeicherten Ereignislog muss sich der Endstand exakt rekonstruieren lassen.
- **Daten-Validierung:** Alle YAML-Dateien werden beim Start gegen ein Schema geprüft.
- **UI-Smoke-Test:** Playwright öffnet die Live-Ansicht einer Bot-Partie und prüft, dass Karte und Nachrichten erscheinen.
- **CI:** GitHub Actions führt alles bei jedem Push aus.

## Roadmap in Phasen

Jede Phase endet mit etwas Lauffähigem. Phasen 1–7 sind das Ziel für den ersten Build mit Fable: Liar's Bar, Poker, Werwolf und Throne of Tokens laufen komplett. Der Rest ist dokumentiert und vorbereitet.

| Phase | Inhalt | Fertig, wenn … |
| --- | --- | --- |
| 1. Fundament | Docker-Setup, Arena-Server, Plugin-Schnittstelle, Event-Log, LiteLLM-Anbindung, Kostenlimits, Zufalls-Bot, Mock-LLM | eine Bot-Partie läuft per CLI durch |
| 2. Liar's Bar | Plugin komplett (Basis + Teufelskarte), Tisch-Chat, Gedanken getrennt, Tests | 4 echte Modelle spielen eine Partie zu Ende |
| 3. Poker | Texas Hold'em mit Side-Pots, Turnier-Blinds, Duplicate-Modus, Hand-Auswertung, Tests | 6 Modelle spielen ein Turnier bis zum Sieger |
| 4. Werwolf | Alle Rollen aus der Rollen-Tabelle, Nacht-Reihenfolge, Erzähler, Hauptmann, Liebespaar, Rollen als YAML, Tests | 8 Modelle spielen mit frei gewählten Rollen zu Ende |
| 5. Zuschauer-UI | Live-Ansicht (3 Spalten), Partie starten inkl. Werwolf-Rollen-Auswahl mit Vorlagen und Balance-Ampel, Bar-, Poker- und Werwolf-Tisch, Replays, Kostenanzeige, Steuerung | man kann jede Partie im Browser einrichten, starten und zuschauen |
| 6. Profile & Wertung | Spielerprofile, Persönlichkeiten, Gedächtnis (3 Ebenen), Elo, Statistiken, Chronist | nach mehreren Partien gibt es eine Rangliste und Erinnerungen |
| 7. Throne of Tokens | Karte, Wirtschaft, Gebäude, Truppen, Kampf, Diplomatie, Ereignisse, Hex-Karten-UI | 4–6 Modelle spielen 60 Runden |
| 8. Game Master & Saisons | KI-Game-Master, Zeitplanung, Saisons, Auszeichnungen, Gott-Modus | Partien laufen automatisch über Tage |
| 9. Mehr Spiele | Liar's Dice, Codenames, Diplomacy-lite, Catan-artig | jedes Spiel läuft mit Elo und Replays |
| 10. Civ-Ausbau | Forschung, Spionage, Steuern, Ränge in einer Nation, Mods | neue Inhalte nur über Daten/Module |
| 11. MOBA | Tick-Modus, Bot-Controller für Mikro, vereinfachte Karte | 2 Teams aus KIs spielen ein Match |

**Offene Fragen**

- Frontend: SvelteKit oder React?
- Welche Modelle sind die erste Standard-Besetzung (z. B. Claude, GPT, Gemini, DeepSeek, Qwen, Llama)?
- Wie hoch soll das Standard-Budget pro Partie sein?
- Sprache der KIs im Spiel: Deutsch, Englisch oder pro Partie wählbar?

## Prompt für Fable

Diesen Prompt zusammen mit diesem Dokument (als `docs/DESIGN.md` exportiert) an Fable geben.

```markdown
Du baust "AIGameVersus", eine Plattform, auf der KI-Modelle gegeneinander Spiele spielen.
Die vollständige Spezifikation steht in docs/DESIGN.md. Lies sie komplett, bevor du anfängst.

Ziel dieses Builds: Phasen 1 bis 7 der Roadmap vollständig und lauffähig.
Das heißt: die Plattform plus vier fertige Spiele – Liar's Bar (Liar's Deck, inkl. Teufelskarte),
Poker (No-Limit Texas Hold'em), Werwolf (alle Rollen aus DESIGN.md, inkl. Amor, Bärenführer,
Hauptmann, und einer Rollen-Auswahl in der UI mit Vorlagen und Balance-Ampel) und
Throne of Tokens (Civ-artig) – mit Zuschauer-UI, Replays, Profilen, Gedächtnis und Elo.
Phasen 8 bis 11 baust du NICHT, aber die Architektur muss sie ohne Umbau ermöglichen
(Plugin-Schnittstelle mit turn_mode "sequential" | "simultaneous" | "tick", Inhalte als Daten,
Hooks, selbst registrierende Tools).

Anforderungen:
- Stack: Python 3.12 + FastAPI + Pydantic, LiteLLM, PostgreSQL, Redis, SvelteKit, Docker Compose.
- API-first: OpenRouter als Standard-Anbieter, Ollama optional über ein Compose-Profil.
- Der Server ist die einzige Wahrheit: jede KI-Aktion wird validiert, ungültige Aktionen
  bekommen eine klare Fehlermeldung und bis zu 2 Korrekturversuche.
- Deterministisch mit Seed (Mischen, Revolver-Kammern, Rollenverteilung, Karte, Kampf-Zufall),
  Event-Sourcing für alle Partien.
- Kostenlimits pro Partie und pro Tag, Live-Kostenanzeige.
- Gedanken, öffentliche und private Nachrichten strikt getrennt. Verdeckte Karten, Rollen und
  Revolver-Kammern dürfen nie in die Observation eines anderen Spielers gelangen.
- Werwolf-Rollen sind Daten (YAML) mit Hooks; neue Rollen erscheinen automatisch in der Auswahl.
- Nachrichten anderer KIs im Prompt klar als Spielerinhalt markieren (Prompt-Injection-Schutz).
- Zufalls-Bot und Mock-LLM für jedes Spiel, damit alles ohne API-Kosten testbar ist.
- Eigene Grafiken für Liar's Bar; keine Namen, Figuren oder Assets aus dem Originalspiel.

Vorgehen:
1. Lege zuerst Repo-Struktur, CLAUDE.md und README.md an (siehe DESIGN.md).
2. Baue Phase für Phase in der Reihenfolge der Roadmap. Schreibe zu jedem System Tests und
   lass sie laufen, bevor du zur nächsten Phase gehst.
   Pflicht-Tests u. a.: Poker-Handauswertung und Side-Pots, Liar's-Bar-Aufdecken und Revolver,
   Werwolf-Nacht-Reihenfolge, jede Rollenfähigkeit, Siegbedingungen inkl. Liebespaar,
   Rollen-Auswahl-Validierung, Civ-Kampfformel, Produktion, Unterhalt, Verträge.
3. Am Ende muss gelten:
   - `docker compose up` startet alles
   - je eine Partie Liar's Bar, Poker, Werwolf (mit allen Rollen) und Throne of Tokens mit
     Zufalls-Bots läuft komplett durch (Integrationstests)
   - jedes der vier Spiele lässt sich in der UI mit echten Modellen einrichten, starten und
     live verfolgen
   - Replays, Rangliste, Profile und Gedächtnis funktionieren spielübergreifend
   - alle Tests sind grün
4. Dokumentiere in CLAUDE.md genau, wie man ein neues Spiel, eine neue Rolle/Variante/Einheit
   und ein neues System hinzufügt, damit spätere Sessions direkt weiterbauen können.
5. Wenn die Spezifikation etwas offen lässt, triff eine sinnvolle Entscheidung und
   notiere sie in docs/DECISIONS.md.
```

**Tipps für den Build**

- Gib Fable den Prompt und das Dokument in einer leeren Repository-Umgebung, mit Zugriff auf Python, Node und Docker.
- Für spätere Erweiterungen: „Lies CLAUDE.md und docs/DESIGN.md, dann baue Phase 8 (Game Master & Saisons).“
- Den OpenRouter-Schlüssel erst eintragen, wenn die Bot-Partien laufen, damit keine Kosten für Debugging entstehen.
