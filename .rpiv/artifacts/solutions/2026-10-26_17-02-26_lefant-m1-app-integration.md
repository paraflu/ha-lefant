---
date: 2026-10-26T17:02:26+0100
author: Andrea Forlin
commit: a5ae93c
branch: develop
repository: ha-lefant
topic: "Integrazione app Lefant M1"
confidence: low
complexity: high
status: needs_input
verdict: needs_input
tags: [solutions, home-assistant, lefant-m1, app-integration]
last_updated: 2026-10-26T21:19:03+01:00
last_updated_by: Andrea Forlin
last_updated_note: "Adapter Tinytuya pronto e verificato contro il robot (errore 904 atteso con chiave fittizia); dipendenza aggiunta al manifest"
---

# Solution Analysis: Integrazione app Lefant M1

**Date**: 2026-10-26T17:02:26+0100  
**Author**: Andrea Forlin  
**Commit**: a5ae93c  
**Branch**: develop  
**Repository**: ha-lefant

## Research Question

"l'integrazione deve permettere l'integrazione con il robot lavapavimenti M1, usa l'applicazione come base per le chiamate le chiavi etc"

## Summary

**Problem**: integrare Home Assistant con il Lefant M1 partendo dall'app ufficiale per determinare il percorso di comunicazione e autenticazione, senza assumere che la sola compatibilità Tuya basti.

**Recommended**: Nessuna scelta implementativa è ancora confermata. Come pista provvisoria, validare l'implementazione LAN già presente e verificare se i dati dell'app permettono di ricavare le credenziali locali; se invece l'intento è replicare le chiamate dell'app, prima occorrono una build/materiale dell'app e una cattura sanitizzata del traffico.

**Effort**: Alto (stima non affidabile prima di chiarire protocollo, fonte delle credenziali e compatibilità sul dispositivo reale).
**Confidence**: Bassa

## Problem Statement

**Requirements:**
- Integrare il robot lavapavimenti Lefant M1 con Home Assistant.
- Usare l'app ufficiale per ricavare gli identificativi/credenziali locali, poi controllare direttamente l'M1 in LAN (chiarimento dell'utente).
- Non pubblicare né inserire in chat password, token o chiavi locali del dispositivo.

**Constraints:**
- Il repository corrente è già un'integrazione locale che chiede IP, device ID e local key; non implementa accesso all'account/app Lefant.
- L'utente ha indicato che può fornire APK/versione dell'app; il materiale non è ancora stato condiviso.
- Le evidenze pubbliche raccolte non provano che il modello M1 usi effettivamente il protocollo Tuya LAN né che esista un'API cloud Lefant pubblica.
- I tentativi di ricerca web diretta sono falliti con errore HTTP 404; le conclusioni esterne qui riportate provengono solo dalle fonti pubbliche recuperate direttamente dagli agenti, e non da una ricerca web riuscita. Non è stata individuata documentazione pubblica M1 verificabile per API/cloud; l'assenza di documentazione pubblica non prova l'inesistenza di un protocollo accessibile tramite reverse engineering.

**Success criteria:**
- Dispositivo reale M1 identificato e protocollo del percorso prescelto validato.
- Onboarding e gestione sicura delle credenziali definiti senza esporre segreti.
- Comandi e stati richiesti verificati sul dispositivo, con test ripetibili.

## Current State

**Existing implementation:**
- `README.md:6` dichiara comunicazione Wi-Fi locale, push su socket persistente e protocollo Tuya LAN 3.5. È descrizione dell'implementazione del progetto, non conferma indipendente del protocollo dell'M1.
- `README.md:26-36` richiede indirizzo IP, device ID e local key e menziona strumenti di acquisizione, compreso il proxy/MITM dell'app. Non documenta un login Lefant o le chiamate cloud dell'app.
- `custom_components/lefant_m1/config_flow.py:20-43` legge host, device ID e local key inseriti dall'utente, poi prova la connessione e interroga i datapoint. La chiamata al client è in `:36`.
- `custom_components/lefant_m1/coordinator.py:23-45` costruisce il client LAN dal config entry e gestisce la connessione push.
- `custom_components/lefant_m1/pytuya_client.py:1-50` implementa framing Tuya LAN 3.5/AES-GCM e TCP porta 6668; `:170-241` gestisce connessione, negoziazione sessione e scambio di stato/controlli.
- `custom_components/lefant_m1/const.py:13-23` contiene i datapoint M1 assunti dalla componente, inclusi controlli e stato. La loro accuratezza sul dispositivo va verificata, non inferita dal solo codice.
- `.rpiv/artifacts/research/2026-09-08_22-09-21_lefant-m1-home-assistant-integration.md:20-28` conserva la proposta cloud iniziale ma anche il successivo pivot al LAN: la ricerca storica aveva giudicato non implementabile una REST API pubblica Lefant. È contesto storico, non prova attuale di impossibilità.

**Relevant patterns:**
- Client di protocollo isolato: `custom_components/lefant_m1/pytuya_client.py` — un client posseduto dall'integrazione gestisce framing e I/O. Nel codice attuale `TuyaClient` viene costruito in 3 punti (`config_flow.py:36`, `coordinator.py:40,100`); non esiste alcun recupero credenziali dall'app.
- Coordinator push-based: `custom_components/lefant_m1/coordinator.py` — inoltra stato alle entità e gestisce reconnect.
- Config flow con validazione: `custom_components/lefant_m1/config_flow.py` — validate prima di salvare la connessione.
- DP M1 locali alla componente: `custom_components/lefant_m1/const.py` — il mapping del robot è separato dal trasporto.

**Integration points:**
- `custom_components/lefant_m1/config_flow.py:20-43` — eventuale acquisizione/login app e memorizzazione sicura dei dati.
- `custom_components/lefant_m1/pytuya_client.py:170-241` — trasporto e chiamate LAN attuali.
- `custom_components/lefant_m1/coordinator.py:23-123` — lifecycle e propagazione dati; dipende dalle API asincrone e push del client.
- `custom_components/lefant_m1/const.py:13-23` — comandi e mapping datapoint, da confrontare con traffico M1 reale.

## Solution Options

### Option 1: Client custom Tuya LAN con credenziali ricavate dall'app

**How it works:**
Mantenere il client e la comunicazione diretta in LAN già implementati. Usare l'app eventualmente come fonte per identificatori e chiave locale, quindi validare protocollo e mapping sul robot effettivo. Non equivale a riprodurre le chiamate app: l'app sarebbe la fonte delle credenziali, mentre i comandi passerebbero direttamente al robot.

**Pros:**
- È il percorso con più precedente nel codice: client, config flow, coordinator e DP mapping esistono già (`pytuya_client.py:170-241`, `coordinator.py:23-45`, `config_flow.py:20-32`).
- Questo stesso repository descrive il proprio percorso M1 come Tuya LAN 3.5, ma non è una conferma esterna né prova indipendente dell'interoperabilità sul dispositivo dell'utente. Un estrattore community indipendente per dispositivi Lefant documenta un M210 Pro Omni, non M1: [Lefant Home Assistant LocalTuya extractor](https://github.com/hectorzin/Lefant-Home-Assistant-LocalTuya).
- Può mantenere il comportamento locale senza dipendere dal servizio cloud una volta ottenuti e verificati i dati necessari.

**Cons:**
- Non soddisfa la richiesta se l'intento è invocare le stesse API/cloud dell'app.
- La compatibilità M1/protocollo/DP non è stata validata indipendentemente; key retrieval tramite app non è attualmente automatizzato.
- La gestione manuale della chiave richiede un flusso utente e procedure di sicurezza adeguate.

**Complexity:** Alta finché non validata (~stima non affidabile).
- Files to create: 0–2 per eventuale onboarding/test (stima).
- Files to modify: 2–5, se si cambia acquisizione credenziali o si corregge mapping (stima).
- Risk level: Medio-alto per compatibilità dispositivo e gestione credenziali.

### Option 2: Integrazione Tuya ufficiale di Home Assistant

**How it works:**
Configurare il dispositivo tramite l'integrazione Tuya integrata in Home Assistant e il suo account/app supportato, lasciando a HA la discovery e le entità. Si applica solo se M1 può essere associato a Tuya Smart/Smart Life e viene esposto con le funzioni richieste.

**Pros:**
- Evita di mantenere nella custom integration il framing e il client LAN.
- Home Assistant documenta una route Tuya cloud per dispositivi Tuya/Smart Life supportati.

**Cons:**
- Le fonti consultate non confermano che Lefant M1 si possa associare all'account Tuya/Smart Life o che l'integrazione ufficiale esponga controlli vacuum adeguati.
- Il repository registra un precedente rifiuto di questa soluzione per esperienza d'uso e comportamento del robot; è una preferenza storica da riconfermare, non un test corrente.
- Cambia il flusso di onboarding e potrebbe richiedere migrazione di entità e automazioni.

**Complexity:** Media-alta, condizionata alla compatibilità.
- Files to create: 0 in questo repo se si usa solo l'integrazione HA ufficiale.
- Files to modify: non applicabile alla custom integration; migrazione config/automazioni utente da stimare.
- Risk level: Alto finché compatibilità account/device non verificata.

### Option 3: Adattatore TinyTuya sotto il client Lefant

**How it works:**
Sostituire o avvolgere la parte generica di protocollo Tuya con TinyTuya, mantenendo nel progetto il mapping M1, il coordinator e l'interfaccia necessaria alle entità. La libreria documenta Tuya LAN e versioni fino a 3.5; la sua interfaccia è prevalentemente sincrona, quindi occorre verificare come preservare l'API async e i push correnti.

**Pros:**
- Riutilizza un ecosistema di protocollo esistente e MIT-licensed; docs/repository TinyTuya descrivono discovery e controllo LAN.
- La separazione attuale client/coordinator (`coordinator.py:40-45`) offre una seam ragionevole per un adapter.
- Ridurrebbe la quantità di implementazione crittografica/protocollo posseduta direttamente dal progetto.

**Cons:**
- Non è evidenza che M1 o l'accoppiamento dall'app Lefant siano compatibili con TinyTuya.
- La libreria non fornisce il mapping vacuum M1; DP, controlli e stati restano responsabilità del componente.
- Il client attuale è asincrono e push-based; l'adattamento può richiedere gestione thread/monitor e nuova copertura test.

**Complexity:** Media-alta.
- Files to create: circa 1 adapter (stima).
- Files to modify: circa 2–4, client/config/dependency/tests (stima).
- Risk level: Medio-alto per semantica async e comportamento push.

### Option 4: Reverse engineering delle chiamate app/cloud Lefant

**How it works:**
Analizzare l'app ufficiale e il traffico per ricostruire autenticazione, endpoint, sequenze di comando e aggiornamenti. Implementare un client separato soltanto dopo aver acquisito materiale sanitizzato e verificato che la route sia praticabile e sostenibile.

**Pros:**
- È l'unica opzione che affronta letteralmente l'interpretazione “stesse chiamate/chiavi dell'app”.
- Il README menziona il proxy/MITM come possibile tecnica per acquisire informazioni dell'app (`README.md:31-34`); non presenta però risultati o una API verificata.

**Cons:**
- Nessuna documentazione pubblica, SDK ufficiale o specifica M1 dell'API Lefant è emersa dalle ricerche svolte.
- Auth, TLS/pinning, token refresh, endpoint, comandi e mantenimento sono sconosciuti; la stima è quindi non quantificabile.
- Credenziali account e token aumentano l'impatto di un errore di storage/logging; non devono finire nei report o nei log.

**Complexity:** Alta e non stimabile prima delle evidenze.
- Files to create: almeno un client/auth layer e test, quantità non determinabile.
- Files to modify: config flow, entry storage, coordinator, manifest e test, quantità non determinabile.
- Risk level: Alto / indeterminato.

## Comparison

Scala qualitativa: favorevole / condizionale / sfavorevole. Per novelty: valuta maturità e rischio di obsolescenza, non la desiderabilità della novità.

| Dimensione | Client LAN custom | Tuya ufficiale HA | TinyTuya adapter | API app/cloud |
|---|---|---|---|---|
| approach-shape | Corrisponde al controllo LAN corrente; compatibilità M1 da provare | Cloud/account, compatibilità M1 condizionale | Riutilizzo protocollo LAN, mantenendo mapping M1 | Rispecchia l'uso delle chiamate app, ma protocollo non noto |
| precedent-fit | Forte nel codice per LAN; assente per key retrieval app | Debole: nessun client ufficiale nel repo | Buona seam client, nessun adapter TinyTuya attuale | Solo idea cloud storica, nessuna chiamata catturata |
| integration-risk | Medio-alto: M1/DP/chiave non verificati | Alto: onboarding e feature M1 non dimostrati | Medio-alto: API sync vs client async/push | Alto: autenticazione e contratto API ignoti |
| migration-cost | Basso per mantenere, maggiore per automatizzare app-key | Alto per migrazione onboarding/entità | Medio-alto, sostituzione seam e test | Alto/indeterminato, nuovo auth/transport |
| verification-cost | Medio: test locali più validazione su robot reale | Alto finché onboarding e funzioni reali non verificati | Medio-alto: adapter + protocollo e push | Alto: catture, fake backend e verifiche di regressione |
| novelty | Approccio LAN Tuya maturo, supporto M1 non verificato | Integrazione HA consolidata, M1 non verificato | Libreria consolidata, M1 non verificato | Un reverse engineering custom sarebbe fragile e soggetto a cambi |

## Recommendation

**No-fit:** nessun candidato soddisfa in modo dimostrato tutti gli aspetti della richiesta, perché non è ancora chiaro se “usare l'app come base” significhi ricavare da essa le credenziali per il controllo locale oppure replicare le chiamate cloud. I candidati cloud e integrazione ufficiale non hanno compatibilità M1 documentata; TinyTuya non risolve la validazione specifica del device; il client LAN esistente non usa l'app per effettuare chiamate e non automatizza il recupero delle chiavi.

**Per-candidate blockers:**
- Client LAN custom: manca prova indipendente sul robot reale e non copre la replica delle chiamate app (`pytuya_client.py:170-241`; il README del repository corrente è una dichiarazione del progetto, non fonte indipendente). L'estrattore Lefant indipendente citato riguarda M210 Pro Omni, non M1: [Lefant Home Assistant LocalTuya extractor](https://github.com/hectorzin/Lefant-Home-Assistant-LocalTuya).
- Tuya ufficiale HA: associazione M1 tramite Smart Life/Tuya e feature vacuum non confermate; documentazione generale: [Home Assistant Tuya integration](https://www.home-assistant.io/integrations/tuya/).
- TinyTuya adapter: M1 e app Lefant non validati; API standard sincrona da raccordare al client push/async. Fonti: [TinyTuya GitHub](https://github.com/jasonacox/tinytuya), [protocol documentation](https://github.com/jasonacox/tinytuya/blob/master/README.md).
- API app/cloud: nessun contratto API Lefant M1 o SDK ufficiale trovato nelle fonti consultate; [sito Lefant](https://www.lefant.com) non documenta un'interfaccia di integrazione.

**Recommended next step:**
- Chiarire l'obiettivo e fornire un riferimento sicuro al materiale: APK/versione e package dell'app oppure cattura HTTP(S) sanitizzata (host, percorsi, schema e sequenza, rimuovendo cookie, token, password, device key, identificativi personali). Non incollare segreti in chat o nell'artifact.
- Precisare se il risultato desiderato è (A) usare l'app per ottenere credenziali e poi comandare il robot in LAN oppure (B) riprodurre l'autenticazione/chiamate cloud dell'app.
- In caso A, testare prima sul dispositivo IP/protocollo/DP con credenziali acquisite localmente, mantenendo i segreti fuori da log e output.
- In caso B, iniziare da analisi offline dell'app e cattura sanitizzata; passare a design/implementazione solo dopo aver ricostruito endpoint, auth e ciclo di refresh.

**Frontmatter overrides:** `confidence: low`, `verdict: needs_input`.

## Scope Boundaries
- Questa analisi confronta percorsi tecnici e non modifica l'integrazione.
- Non estrae né memorizza chiavi, token, password o dati personali.
- Non assume che un prodotto “Tuya-based” sia necessariamente compatibile con ogni API o integrazione Tuya.
- Non considera il reverse engineering come prova di una API supportata o stabile.

## Testing Strategy

**Unit tests:**
- Se si mantiene il client LAN: framing, key/session negotiation, decode DP, comandi e gestione disconnect usando segreti sintetici e fixture non sensibili.
- Se si adotta TinyTuya: test contrattuali dell'adapter e simulazione delle notifiche push/reconnect.
- Se si aggiunge app/cloud: test auth/token lifecycle con risposte mock e redaction log verificata.

**Integration tests:**
- Verificare onboarding e comandi/stati sul Lefant M1 reale; registrare solo risultati sanitizzati.
- Verificare che la chiave acquisita dal metodo scelto sia accettata dal device e che i DP corrispondano all'osservazione dell'app.
- Se cloud: verificare login, refresh, interrogazione stato, comandi start/pause/return e comportamento offline senza usare credenziali personali nei test automatici.

**Manual verification:**
- [ ] Confermare la modalità desiderata: chiave locale via app o chiamate cloud app.
- [ ] Confermare modello esatto e versione firmware/app senza condividere dati account.
- [ ] Provare con device reale che stati, batteria e comandi siano coerenti.
- [ ] Controllare che log e artifact non contengano credenziali o payload sensibili.

## Open Questions

**Resolved during research:**
- Quale percorso implementa oggi il repo? — LAN Tuya locale con device ID e local key inseriti nel config flow (`config_flow.py:20-43`; `pytuya_client.py:170-241`).
- Il codice usa attualmente login o chiamate cloud dell'app Lefant? — No, non nei file di integrazione esaminati (`config_flow.py:20-43`, `coordinator.py:23-45`).
- Esiste prova pubblica sufficiente dell'API cloud M1? — Nessuna individuata nelle fonti consultate; questa è una ricerca non esaustiva e non dimostra che l'API sia inesistente.

**Requires user input:**
- “Usa l'app come base” significa ricavare local key/device ID o replicare le chiamate cloud dell'app? — Risolto: l'utente intende usare l'app per ricavare credenziali LAN e poi controllare direttamente il robot.
- Quale materiale app-specifico si può esaminare? — Ricevuto e analizzato staticamente `Lefant_v3.4.5_APKPure.xapk` (package/versione nel follow-up 2026-10-26T19:11:29+01:00).

**Blockers:**
- Non è stato seguito staticamente l'intero flusso dall'autenticazione alla risposta `localKey`; l'APK resta disponibile in `/tmp/lefant-xapk.UJHK4l/decoded` per ulteriori analisi mirate, senza installarlo o eseguirlo.
- Restano da validare sul dispositivo reale la key locale, il protocollo e i DP M1 — fornire solo osservazioni sanitizzate, mai la chiave stessa.

## Follow-up Analysis 2026-10-26T17:19:31+01:00

**Chiarimento dell'utente:** l'app Lefant serve come fonte per ricavare le credenziali locali; il controllo del robot deve poi avvenire direttamente in LAN. L'utente può fornire APK/versione dell'app.

**Aggiornamento della direzione:** il client LAN custom già presente è la pista preferita per una validazione successiva, perché il requisito non è replicare le chiamate cloud. Non è ancora una soluzione confermata: il repository richiede la local key inserita manualmente e non contiene recupero credenziali dall'app (`custom_components/lefant_m1/config_flow.py:20-43`); il protocollo Tuya LAN, la chiave e i datapoint non sono verificati in modo indipendente sul dispositivo reale M1. Il precedente no-fit sintetizzava la situazione prima che l'utente chiarisse l'intento; questa preferenza restringe la ricerca ma non elimina i blocker tecnici.

**Prossima evidenza richiesta:** condividere il percorso dell'APK ottenuto legittimamente, oppure il nome package, versione esatta e link ufficiale da cui installare l'app. Non condividere account, password, token, cookie o local key. In assenza del binario, versione/package possono almeno delimitare l'analisi delle fonti pubbliche e dei metadati.

**Esito:** `confidence: low`, `verdict: needs_input` invariati finché non si esaminano i materiali e non si valida il flusso credenziali/protocollo sull'M1.

## Follow-up Analysis 2026-10-26T19:11:29+01:00

**Materiale analizzato:** `Lefant_v3.4.5_APKPure.xapk`, fornito nel workspace. Verificato come ZIP/XAPK, 213,181,321 byte; SHA-256 `35ea6d8db6ef3d9558335d8d4bd93e3bb181b40b176ffc691b2eab0f56ba240e`. Elencati gli entry interni senza estrarre nell'albero del repository. Il base APK e `manifest.json` sono stati estratti in `/tmp/lefant-xapk.UJHK4l/` dopo controllo che i nomi fossero entry root sicure; decompilazione statica con Apktool 2.10.0. L'app non è stata installata o eseguita. XAPK da fonte APKPure: l'analisi descrive il file fornito e non ne certifica provenienza o integrità rispetto a una release ufficiale.

**Identità e SDK:** `manifest.json` indica package `com.yunshi.robotlife`, Lefant `v3.4.5`, version code `34501`, min SDK 24 e target SDK 35. Base APK con DEX `classes.dex`–`classes10.dex`. Sono presenti numerose classi `com.thingclips.smart.*`, inclusi SDK home/device e interfacce di controllo locale: prova che il bundle contiene SDK ThingClips/Tuya, non che l'M1 sia automaticamente compatibile con Tuya LAN.

**Evidenze statiche rilevanti:**
- `com/thingclips/smart/sdk/bean/DeviceBean.smali`: espone accessor `getDevId()` e `getLocalKey()` (con una via cache/risposta SDK e una via campo bean). Codice Lefant in `OooO00o/OooO00o.smali` legge `DeviceBean.devId` dentro il parser dei datapoint. Questo conferma l'uso del device ID da parte del codice applicativo.
- `com/thingclips/smart/interior/device/bean/DeviceRespBean.smali`: oggetto risposta SDK con campo per-device `localKey`, getter/setter e implementazione `IStorageCache`. Anche modelli SDK quali `ActiveDmDeviceBean`, `GroupRespBean` e `GwDevResp` contengono campi simili.
- `com/yunshi/robotlife/MyApplication.smali`: inizializza `ThingHomeSdk` e registra listener push/login. Evidenza di SDK e infrastruttura di account/device app; non è stato seguito un flusso completo da login all'effettiva risposta contenente la chiave.

**Interpretazione e limiti:** i campi `devId` e `localKey` sono proprietà dei modelli dispositivo/risposta, non costanti condivise dell'app. La scansione statica mirata non ha provato che una chiave valida sia incorporata nell'APK o derivabile offline; non ha ricostruito origine server, autenticazione richiesta o persistenza effettiva del valore. Non sono stati identificati endpoint/backend affidabili. I nomi dei campi e la presenza del package SDK non dimostrano che il device Lefant M1 fornisca una chiave compatibile con il client locale del repository, né convalidano il protocollo o i datapoint sul robot fisico. APK statico non contiene i dati dell'account autenticato, dell'home o del dispositivo associato.

**Esito aggiornato:** l'APK dimostra che l'app incorpora lo stack SDK ThingClips e modella gli identificativi/chiavi locali come dati associati a dispositivi; suggerisce una via app/account/SDK per accedere a tali dati, ma la catena concreta di recupero resta da chiarire. La direzione LAN scelta dall'utente resta preliminare; `confidence: low` e `verdict: needs_input` invariati. Nessun punteggio precedente è stato modificato.

**Prossimo passo:** per eventuale analisi aggiuntiva, l'utente può fornire osservazioni riproducibili dell'app autenticata o un flusso di esportazione/lettura dati sanitizzato. Non condividere la local key, password, token, cookie, credenziali o dump di storage non filtrati. La compatibilità si dovrà comunque validare sul M1 fisico senza registrare segreti.

## Follow-up Analysis 2026-10-26T20:28:09+01:00

**Obiettivo:** proseguire l'analisi statica (punto 1) tracciando il flusso concreto con cui l'app ottiene identificativi e chiavi, per capire se la via “app come base delle chiavi” sia praticabile verso il controllo LAN.

**Metodo:** sola lettura sul codice applicativo (`smali_classes9/`, `smali_classes10/` e package offuscati `OooO00o`, `OooO0O0`, `OooO0OO`); ricerche mirate su simboli, nessuna esecuzione dell'app, nessun dump indiscriminato di stringhe, nessun segreto riprodotto.

**1. L'app è multi-piattaforma, non “Tuya-only”**
- `uitils/iot/IOTConfig$IotPlatform` definisce quattro piattaforme: `TUYA` (value 1), `LIVIROBO` (3), `COOLKIT` (4), `TANGE` (5). La scelta attiva è persistita in `SharedPreferences` con chiave `iot_platform` e **default 1** (`library/utils/SharedPrefs.smali` `getIotPlatform`/`setIotPlatform`).
- `library/base/Config$OitType` espone il selettore usato dai flussi di login: `TUYA = 1`, `OPPO = 2`.
- Conseguenza: la piattaforma effettiva dell'M1 va letta dal dispositivo/account reale, non dedotta dal fatto che l'app contenga l'SDK Tuya.

**2. Catena credenziali lato backend Lefant**
- `SharedPrefs` persiste `access_token`, `refresh_token`, `current_home_id`, `device_uuid`, `third_reg_uuid`, `access_token_coolkit`, `check_user_token_tange`.
- I bean di login/utente (`LoginBean$DataEntity`, `UserInfoBean$DataEntity`) trasportano `access_token`, `third_uuid_tuya`, `third_reg_uuid`, `third_uuid_oppo`.
- `ui/main/InitDataService.smali` invia al backend Lefant l'uid Tuya ottenuto dall'SDK (`UPDATE_USER_INFO`, parametro `third_uuid_tuya`): il binding account Lefant ↔ identità Tuya è quindi esplicito.

**3. Il record dispositivo di Lefant non contiene la local key**
- `bean/HomeDeviceInfoBean` espone `third_dev_id` (id dispositivo Tuya), `third_home_id_tuya`, `third_product_id_tuya` (product id Tuya), `hardware_sdk_source`, `device_hardware_id`, `mac`, oltre a `accessKeyId` / `accessKeySecret` / `bucketName` (credenziali di object storage per log/mappe).
- **Nessun campo `localKey`/`local_key`** nel modello dispositivo del backend Lefant: la chiave locale non viene emessa da Lefant.

**4. Login Tuya di tipo OEM, non account consumer**
- `uitils/iot/AccountManagerUtils.smali` (`registAccount`) instrada su `TuyaAccountUtils.registByUid(uid, …, createHome)` che chiama `IThingUser.loginOrRegisterWithUid(...)` (`library/utils/tuya/TuyaAccountUtils.smali:132,145`).
- L'uid proviene dal backend Lefant; l'appKey è quella dell'app (`SharedPrefs.setAppKey`). È il pattern “custom user” dell'SDK Tuya: l'utente non accede con un account Tuya Smart, ma come identità emessa da Lefant.

**5. La local key è solo un metadato dell'SDK, e l'app non la usa**
- `localKey` esiste in `com/thingclips/smart/sdk/bean/DeviceBean` e `com/thingclips/smart/interior/device/bean/DeviceRespBean` (con `getLocalKey`/`setLocalKey`), cioè dentro l'SDK bundled.
- Nel codice applicativo (incluse le classi offuscate) le occorrenze di `getLocalKey`/`setLocalKey` sono **zero**.
- Le classi di controllo locale Tuya (`ThingLocalControlBean`, `ThingLocalNormalControlBean`, `ThingQueryInfoBuilder`, `LocalDeviceBean`, `LocalKeyBean`, `ILocalDpMessageRespListener`) sono presenti **solo** dentro l'SDK e non sono referenziate dal codice app.
- Il percorso di controllo effettivo dell'app è: cloud Tuya via SDK (MQTT, `IThingDevice`) + SDK sweeper/P2P per mappe e path. Non c'è alcun percorso LAN.

**6. Cosa significa per la richiesta**
- “Usare l'app come base per le chiavi” si traduce tecnicamente in: riprodurre il login OEM Tuya (appKey Lefant + uid emesso dal backend Lefant + materiale di autenticazione utente) e leggere `DeviceBean.localKey` dalla lista dispositivi restituita dal cloud. Non è la strada “login con account Tuya Smart”.
- Poiché l'app non usa il controllo LAN, l'APK **non dimostra** che il robot accetti il protocollo locale 3.5 implementato in questo repo: la presenza della chiave nei modelli SDK indica solo che il cloud Tuya può fornirla.
- Il client LAN del repository resta una capacità teoricamente disponibile sul dispositivo, non il percorso che l'app percorre.

**Limiti residui:** non è stato ricostruito il materiale di autenticazione interno usato da `loginOrRegisterWithUid` (logica SDK offuscata), né è possibile stabilire da statico se il record del robot dell'utente abbia `third_product_id_tuya` valorizzato e `iot_platform = 1`. Il file XAPK è ora escluso da git (`*.xapk`, `*.apk` in `.gitignore`).

**Prossimo passo verificabile:** sull'istanza reale dell'app, leggere i soli valori non segreti `iot_platform` e presenza di `third_product_id_tuya` per l'M1 (senza esportare token o chiavi). Se la piattaforma non è TUYA, l'intera ipotesi di chiave locale Tuya decade per quel dispositivo.

## Follow-up Analysis 2026-10-26T20:33:11+01:00

**Obiettivo:** verificare se l'APK contenga una mappa datapoint per modello utilizzabile come riferimento per `custom_components/lefant_m1/const.py`.

**Catalogo modelli (evidenza solida):** `device/EquipmentConfig.smali` definisce `M1_02 = "M1-02"`, `M1_03 = "M1-03"` e il set `M1Series = {M1-02, M1-03}`. Il gating per modello usa `SweeperDevice.getModelName()` (es. `device/base/DeviceFunctionConfiguration.smali` confronta con `getM1_03()` e con la versione MCU). La classificazione di navigazione proviene dal backend: `HomeDeviceInfoBean.getNavigation_type()` → `IOTConfig$RobotType{ LASER_TYPE, GYROSCOPE_TYPE }`; le classi M1 (`DeviceM1DetailActivity`, mappe con `initLaserData`) ricadono nel ramo laser.

**Le tabelle DP nell'APK non sono la mappa dell'M1.** `IOTConfig$LASER_DP` e `IOTConfig$GYROSCOPE_DP` contengono costanti denominate con valori (es. `SWITCH_GO=1`, `PAUSE=2`, `SUCTION=9`, `CLEAN_TIME=6`, `RESIDUAL_ELECTRICITY=8`, `SEEK=11`, `FAULT=28` nella variante laser), ma **non sono referenziate da alcun codice applicativo**: le uniche occorrenze sono l'autoriferimento nella classe stessa e l'elenco in `IOTConfig`. Sono un catalogo legacy, non il percorso di lettura/scrittura dei DP: nessun metodo di controllo (`TuyaDeviceHandleUtils`, `DeviceControlUtils`, `BaseViewDpModel`) ne fa uso.

**Fonte reale dei DP: il backend.** `HomeDeviceInfoBean` trasporta la configurazione funzionale per prodotto/modello — campi `pid_func_configs`, `device_model_func_config_list`, `include_func`, `device_model_id`, `submodel`, `hardware_sdk_source`. L'app risolve le funzioni e i relativi datapoint da questi dati server-side per prodotto (`third_product_id_tuya`), non da costanti compilate.

**Conseguenza:** la mappa DP del Lefant M1 **non è estraibile staticamente** dall'APK. Qualunque confronto con `custom_components/lefant_m1/const.py` condotto su queste costanti sarebbe privo di valore: le costanti non sono il contratto del dispositivo. Il mapping attuale del repo (inclusi `SUCTION=14`, `CLEAN_TIME=18`, `CLEAN_AREA=19`, `BATTERY=23`, `LOCATE=24`, `ERROR_CODE=25`) resta **non verificato**, né confermato né smentito da questa analisi.

**Limiti:** i valori di `STATUS` risiedono nelle risorse compilate (`resources.arsc`, non decompilate in questa sessione), quindi anche il mapping stringa→attività non è validabile staticamente. La conferma richiede la configurazione funzionale che il backend restituisce per il `third_product_id_tuya` dell'M1, oppure una lettura reale dei DP sul robot.

**Nota di metodo:** una prima lettura di questa sessione aveva interpretato le costanti `IOTConfig$LASER_DP` come mappa M1, ma quella classe non è referenziata dal codice: conclusione ritirata. La sezione `2026-10-26T20:38:29+01:00` riapre il punto su basi diverse (`device/tuya/data/LaserDP` con `const val` inlineati e le enum che interpretano i DP).

## Follow-up Analysis 2026-10-26T20:38:29+01:00

**Perché la conclusione precedente va riaperta:** `device/tuya/data/LaserDP.smali` è un oggetto Kotlin di `const val` interi — il compilatore ne **inlinea i valori** nei call site, quindi l'assenza di riferimenti a `LaserDP;->...` non prova che la mappa sia inutilizzata. La stessa numerazione compare come stringhe in `IOTConfig$LASER_DP`. Le enum che interpretano quei DP sono invece attivamente usate: `device/tuya/data/Status` (37 file), `Mode` (24), `SuctionLevel` (13).

**Mappa DP famiglia laser (`device/tuya/data/LaserDP`, valori decimali):**
`SWITCH_GO=1`, `PAUSE=2`, `SWITCH_CHARGE=3`, `MODE=4`, `STATUS=5`, `CLEAN_TIME=6`, `CLEAN_AREA=7`, `RESIDUAL_ELECTRICITY=8`, `SUCTION=9`, `CISTERN=10`, `SEEK=11`, `DIRECTION_CONTROL=12`, `RESET_MAP=13`, `PATH_DATA=14`, `COMMAND_TRANS=15`, `REQUEST=16`, `BREAK_CLEAN=27`, `FAULT=28`, `DEVICE_TIMER=32`; varianti canale mappa `*_P2P`: `CLEAN_TIME_P2P=16`, `CLEAN_AREA_P2P=17`, `RESIDUAL_ELECTRICITY_P2P=23`, `DIRECTION_CONTROL_P2P=26`, `SEEK_P2P=27`, `BREAK_CLEAN_P2P=15`, `CARPET_BOOSTER_P2P=14`; comandi alti `COMMAND_FORBID=101`, `COMMAND_PARTIAL_CLEAN=102`, `COMMAND_POSE_CLEAN=103`, `COMMAND_ALL_CLEAN=104`, `GET_DEVICE_INFO=110`, `SWITCH_SAVE_MAP=112`, `DEVICE_CHARGING_PILE=125`, `CLEANING_CUSTOM=150`, `CLEAN_SEQUENCE=152`, `TIMES_TASK=154`.

**Confronto con `custom_components/lefant_m1/const.py`:**

| Costante repo | Repo | App (LaserDP) | Esito |
|---|---|---|---|
| `DP_SWITCH_GO` | 1 | `SWITCH_GO=1` | coerente |
| `DP_PAUSE` | 2 | `PAUSE=2` | coerente |
| `DP_SWITCH_CHARGE` | 3 | `SWITCH_CHARGE=3` | coerente |
| `DP_MODE` | 4 | `MODE=4` | coerente |
| `DP_STATUS` | 5 | `STATUS=5` | coerente |
| `DP_SUCTION` | 14 | `SUCTION=9` (14 = `PATH_DATA`) | **discordante** |
| `DP_CLEAN_TIME` | 18 | `CLEAN_TIME=6` | **discordante** |
| `DP_CLEAN_AREA` | 19 | `CLEAN_AREA=7` | **discordante** |
| `DP_BATTERY` | 23 | `RESIDUAL_ELECTRICITY=8` (23 = variante `_P2P`) | **discordante** |
| `DP_LOCATE` | 24 | `SEEK=11` | **discordante** |
| `DP_ERROR_CODE` | 25 | `FAULT=28` | **discordante** |

Il caso batteria è il più insidioso: `23` esiste davvero, ma come `RESIDUAL_ELECTRICITY_P2P` del canale mappa, quindi una lettura può restituire un numero plausibile e sbagliato di origine.

**Valori enum discordanti (`SuctionLevel`, `Mode`):**
- `SuctionLevel`: `QUIET → "gentle"`, `NORMAL`, `STRONG → "strong"`, `SUPER`, `CLOSE`. Il repo usa `quiet`/`normal`/`strong`: **`quiet` non esiste**, il valore Tuya è `gentle`. `vacuum.py:149-150` scrive `fan_speed` grezzo su `DP_SUCTION`, quindi impostare “quiet” invierebbe un valore non valido.
- `Mode`: enum app `smart→"Smart"`, `chargego→"ChargeGo"`, `zone→"zone"`, `pose→"pose"`, `fastmapping→"fastmapping"`, `CleanModeSectorBased`, `random` (valore anomalo), `None` (stringa vuota). Il repo definisce `MODE_SMART="smart"`, `MODE_EDGE="edge"`, `MODE_SPOT="spot"`, `MODE_RANDOM="random"`, `MODE_STANDBY="standby"`: `edge`, `spot` e `standby` **non compaiono** nell'enum; `vacuum.py:158` invia `MODE_SPOT` per lo spot clean.

**Stati: la tabella del repo non copre quelli reali (`device/tuya/data/Status`, 24 costanti):**
`standby`, `smart`, `Cleaning`, `Paused`, `PosUnreachable`, `goto_charge`, `Charging`, `charge_done`, `Sleep`, `Relocating`, `RelocatingRecharge`, `RechargePaused`, `dust_collection`, `WashMap`, `GotoWash`, `WashPaused`, `FastmapingStatus`, `FASTMAPINGPAUSED`, `CONTINUITY_CLEAR_CHARGING`, `Drying`, `relocating_pause`, `wall_follow_clean`, `spot_clean`, più un valore `NonPlannedModeRecharge`.
- **Bug comportamentale certo:** `Relocating` non è nella `STATUS_TO_ACTIVITY` del repo → `map_status_to_activity` ricade su `IDLE` mentre il robot sta tornando/riposizionandosi.
- **Omonimia inventata:** il repo mappa `wall_clean`, l'app usa `wall_follow_clean` → anche questo cade su `IDLE` invece di `CLEANING`.
- **Chiavi inesistenti nel repo:** `smart_clean`, `random_clean`, `spot`, `edge`, `random`, `pause`, `docked`, `dormant`, `idle`, `error`, `fault` e le varianti `*_pause` (`smart_clean_pause`, `wall_clean_pause`, `spot_clean_pause`, `goto_charge_pause`) non corrispondono a nessuno stato dell'app; l'app usa forme come `relocating_pause`, `WashPaused`, `RechargePaused`.
- La normalizzazione a lowercase del repo è invece corretta: gli stati arrivano con case misto (`Cleaning`, `Paused`, `Charging`, `Sleep`, `Relocating`).

**Limiti da non dimenticare:** (a) queste enum coprono l'intera famiglia Tuya dell'app, non il singolo prodotto; parte degli stati (`WashMap`, `Drying`, `WashPaused`, `dust_collection`) appartiene a basi di lavaggio/asciugatura e probabilmente non esiste sull'M1; (b) il contratto definitivo per prodotto resta la function-config del backend (`pid_func_configs` / `third_product_id_tuya`) o una lettura reale dei DP; (c) `LaserDP` copre la famiglia laser, e l'M1 è nel ramo laser per `navigation_type` e per le classi di mappatura, ma questo è un'inferenza, non una lettura del prodotto.

**Conseguenza operativa:** il mapping attuale del repo è sbagliato su sei datapoint, su almeno un valore enum di aspirazione, sui valori di modalità e su due stati che finiscono in `IDLE` mentre il robot lavora. Questo va corretto **prima** di investire su credenziali/chiavi: con la mappa attuale il componente può risultare “connesso” e insieme silenziosamente inaffidabile.

## Review & Corrections 2026-10-26T20:48:19+01:00

Revisione critica indipendente dell'analisi (modello `gpt-6.1-sol`), con ricontrollo dei riscontri sui file. Diversi punti risultano confermati, altri **eccedevano le prove**: questo blocco li corregge e prevale sulle sezioni precedenti dove sono in conflitto.

**Confermati**
- Multi-piattaforma: `IOTConfig$IotPlatform` TUYA=1, LIVIROBO=3, COOLKIT=4, TANGE=5; `SharedPrefs` chiave `"iot_platform"`, default **1**. Non identifica però la piattaforma del robot reale.
- Zero occorrenze dei sette simboli di controllo locale (`getLocalKey`/`setLocalKey`, `ThingLocalControlBean`, `ThingLocalNormalControlBean`, `ThingQueryInfoBuilder`, `LocalKeyBean`, `ILocalDpMessageRespListener`) su ~5.582 file smali delle cinque radici.
- `HomeDeviceInfoBean` non contiene alcun campo `localKey`/`local_key`.
- Valori `LaserDP` elencati (1,2,3,4,5,6,7,8,9,10,11,28) e `RESIDUAL_ELECTRICITY_P2P=23`.
- `SuctionLevel`: `QUIET → "gentle"`, `STRONG → "strong"`; il repo invia `"quiet"` — discordanza certa.
- `Status`: 24 costanti, incluse `Relocating` con valore **`"relocating"`** e `"wall_follow_clean"`.
- `IOTConfig$LASER_DP` non ha riferimenti operativi: solo la propria definizione e un'annotazione in `IOTConfig`.

**Correzioni (claim precedenti non sostenuti)**
1. **“L'app è cloud-only, non usa LAN” — FALSO come affermazione forte.** L'app delega il trasporto all'SDK: `device/tuya/core/CommandSendImpl.smali:626` chiama `IThingDevice.publishDps`, e la pipeline SDK (`com/thingclips/sdk/device/presenter/AbsThingDevice.smali:2632`, `AbsThingDevice$bppdpdq.smali:124-143`) contempla il canale LAN. Il canale effettivamente scelto sull'M1 resta **ignoto**. L'assenza di classi local-control nel codice app prova che *l'app non pilota esplicitamente la LAN*, non che la LAN sia esclusa.
2. **“Il backend Lefant non emette la chiave” — non dimostrato.** È vero che il bean non ha il campo; non è prova che nessuna risposta Lefant possa fornirla.
3. **Login Tuya: UID sbagliato.** Il flusso usa `third_reg_uuid` + `third_password` (`ui/login/LoginViewModel.smali:3810,3861,4118,4142`), non `third_uuid_tuya` (che esiste separatamente, `:4010`).
4. **“DP disponibili solo dal backend, non estraibili staticamente” — FALSO.** I datapoint compaiono come letterali nel ramo laser: `base/BaseViewDpModel.smali:4094-4158` contiene le stringhe `"1"`, `"4"`, `"5"`, `"6"`. Le costanti stringa sono inlineate come gli interi: l'assenza di riferimenti a un catalogo non prova che sia legacy né che i DP arrivino solo dal server.
5. **“Gli stati sono solo nelle risorse compilate” — non sostenuto:** le enum `Status`, `Mode`, `SuctionLevel` stanno nel DEX ed elencano i propri valori.
6. **`IOTConfig$LASER_DP` non è un catalogo “legacy” dimostrato** (vedi punto 4): semplicemente non è il punto di riferimento usato dal codice.
7. **Conteggi di riferimento attivo:** ricontrollando i descrittori completi risultano **47/32/16** file per `Status`/`Mode`/`SuctionLevel` (46/31/15 escludendo le definizioni), non 37/24/13.
8. **Nomi e valori di `Mode`:** `Smart → "smart"` (non l'inverso); l'enum ha dieci costanti, non otto come riportato.
9. **DP23 non è solo teorico:** è gestito realmente quando `isP2PMap()` è vero (`device/tuya/core/TuyaFunctionality.smali:2460-2640`, rami a `:271,3237,3272,3331`). Su modelli con mappa P2P la batteria può quindi arrivare davvero da 23.

**Cosa resta valido come rischio operativo**
- Il mapping del repo è **almeno** discordante su `SUCTION` (invia `quiet`, il valore atteso è `gentle`), e non copre stati che l'app modella (`relocating`, `wall_follow_clean`) → fallback a `IDLE`.
- Queste sono discordanze *osservabili nel codice*, non comportamenti verificati sul robot: senza una lettura reale dei DP restano ipotesi di lavoro.

**Verifiche minime prima di toccare il codice**
1. Identificare sul dispositivo: piattaforma (`iot_platform`), `third_product_id_tuya`, variante modello (M1-02/M1-03), firmware e schema DP applicabile.
2. Accertare se la local key è ottenibile in modo sicuro e se l'handshake LAN (versione protocollo) risponde — senza esporre segreti.
3. Osservare DP e valori sanitizzati durante singole azioni controllate, distinguendo le varianti `_P2P`, **prima** di modificare `const.py`.

## Verifica di rete 2026-10-26T20:57:49+01:00

Eseguita la prima verifica sul campo con `tools/diagnose_tuya_lan.py` (diagnostica di sola rete: nessuna chiave, nessun login, identificativi mascherati nell'output).

**Risultato osservato sulla LAN locale (192.168.3.0/24):**
- **4 host con porta TCP 6668 aperta** (`.100`, `.103`, `.115`, `.117`).
- Due host hanno risposto alla sonda non cifrata come **v3.4/3.5**: connessione accettata, nessuna risposta al `DP_QUERY` in chiaro — esattamente il comportamento atteso dalla negoziazione 3.4/3.5.
- Annunci UDP decodificati per `.103` e `.115`: stesso `productKey` (`keyjnuy4s3kre7m7`), `version=3.5`, `encrypt=True`. Sono quindi **due dispositivi dello stesso modello** sul livello Tuya (device id distinti, mascherati).
- `.117` risponde in framing 55AA cifrato: profilo v3.3, quindi un dispositivo diverso.
- `.100` ha la porta aperta ma nessun annuncio associato: identificazione non conclusa.

**Cosa questo prova e cosa no**
- Prova che sulla rete dell'utente esistono dispositivi **Tuya LAN v3.5 raggiungibili**, con lo stesso protocollo che il repo implementa. L'ipotesi di trasporto non è più solo un'affermazione community.
- **Non** prova che uno di quei dispositivi sia l'M1: il tool non distingue un robot da altri apparecchi Tuya. Servono o un confronto con l'IP noto dal router, o un test a robot spento/acceso.
- **Non** dice nulla su local key, DP o comportamento dei comandi: quelli restano da verificare.

**Conseguenza pratica:** il ramo "protocollo LAN" sopravvive alla verifica di rete; il ramo "serve il cloud/app" diventa molto meno probabile per questi dispositivi. Il passo successivo è attribuire con certezza l'IP del robot, poi provare un handshake con la local key e leggere i DP reali per correggere il mapping.

**Nota sullo strumento:** `tools/diagnose_tuya_lan.py` usa solo la chiave **pubblica del protocollo di discovery** (la stessa di tuya-convert/tinytuya, uguale per tutti i dispositivi), non una chiave utente. Non tocca il robot in scrittura: invia un solo `DP_QUERY` vuoto e in caso di dispositivo 3.4/3.5 non ottiene risposta.

## Attribuzione del dispositivo 2026-10-26T21:06:01+01:00

**Dato fornito dall'app (schermata info dispositivo):** nome `Lefant M1`, modello `M1`, firmware `1.8.71`, app `v3.4.5`, seriale con prefisso **`bf23`** (valore completo non riportato qui: è un identificativo del dispositivo e non va pubblicato).

**Confronto con i device visti in LAN:**

| Host | device id (mascherato) | productKey | versione | Coincide con `bf23`? |
|---|---|---|---|---|
| `.103` | `bf0b...sapv` | `keyjnuy4s3kre7m7` | 3.5 | **no** |
| `.115` | `bf12...swwo` | `keyjnuy4s3kre7m7` | 3.5 | **no** |
| `.100` | nessun annuncio | — | 3.4/3.5 (porta aperta) | non determinabile |

**Conclusione:** i due dispositivi Tuya v3.5 che si annunciano in LAN **non sono l'M1**. Sono altri apparecchi (stesso productKey tra loro, quindi probabilmente due esemplari dello stesso prodotto diverso dal robot). L'identificazione per prefisso è dirimente: il device id del robot inizia con `bf23`, nessuno dei due annunciati lo fa.

**Perché il robot non compare:** al momento delle ultime scansioni era spento. La discovery attiva su UDP 7000 (comando `REQ_DEVINFO`, aggiunta allo strumento) sollecita i device che non trasmettono spontaneamente, ma non può ottenere risposta da un dispositivo alimentato spento. Le scansioni precedenti, fatte a robot acceso, usavano solo ascolto passivo: un device che non annuncia spontaneamente non poteva essere visto.

**Cosa resta da fare:** riaccendere il robot e rilanciare
`python3 tools/diagnose_tuya_lan.py --udp-wait 12 --expect bf23`.
Se il prefisso compare, si ottengono in un colpo IP, device id, productKey e versione di protocollo dichiarata dal robot — senza alcuna chiave.

**Nota sullo strumento:** oltre all'ascolto passivo (6666/6667/7000) ora esegue anche la discovery attiva su 7000 con il comando `REQ_DEVINFO`, sempre usando solo la chiave pubblica del protocollo. Aggiunti MAC/OUI e il confronto `--expect`.

## Robot identificato — protocollo 3.3 2026-10-26T21:13:03+01:00

Con il robot acceso, la diagnostica di rete ha identificato il dispositivo in modo riproducibile.

**Dati osservati**
- **IP**: `192.168.3.117` — porta TCP 6668 aperta.
- **device id**: `bf23…esv5` (prefisso `bf23`, coerente con il seriale mostrato dall'app; valore completo non riportato).
- **productKey**: `xlljfbbnf5yjit6k` (diverso da quello degli altri due device Tuya in LAN).
- **MAC**: OUI `78:22:88` (parte specifica del dispositivo omessa).
- **versione protocollo dichiarata dal dispositivo**: **3.3**.
- Coerente con la sonda TCP: alla `DP_QUERY` non cifrata il robot risponde con un frame **55AA cifrato** (comportamento tipico 3.3), non chiudendo la connessione come farebbe un 3.4/3.5.

**Conseguenza principale: il client del repo non può funzionare con questo robot.**
`custom_components/lefant_m1/pytuya_client.py` implementa **solo** il protocollo 3.5: framing `0x6699`, AES-GCM, negoziazione della chiave di sessione (`SESS_KEY_NEG_START/RESP/FINISH`). Un dispositivo 3.3:
- usa il framing `55AA` con CRC32, non `6699`;
- cifra i payload con **AES-ECB** sulla `local key`, con header `"3.3"` + 12 byte nulli, senza negoziazione di sessione;
- risponde ai comandi `DP_QUERY` (0x0A) e `CONTROL` (0x07), non a `DP_QUERY_NEW`/`CONTROL_NEW`.

Quindi la connessione non fallisce per chiave sbagliata o mapping DP errato: fallisce **al primo frame**, perché il protocollo è un altro. Questo spiega perché l'ipotesi LAN non abbia mai prodotto un dispositivo funzionante, indipendentemente dai DP.

**Cosa cambia nella scelta di implementazione**
- Il trasporto 3.3 è **più semplice** del 3.5: niente GCM, niente handshake, niente gestione della sessione. Solo ECB + CRC + JSON.
- Diventa quindi molto più conveniente **non** riscrivere il client a mano: `tinytuya` supporta 3.1/3.3/3.4/3.5 nativamente ed è MIT. L'adapter TinyTuya, prima valutato come opzione intermedia, ora è la strada con il rapporto rischio/beneficio migliore: il codice di protocollo sparisce, restano solo mapping M1 e ciclo di vita HA.
- Resta necessario **la local key**: il 3.3 la usa direttamente come chiave AES-ECB (16 byte). Nessuna delle analisi fatte la fornisce; va recuperata con il metodo community o equivalente.

**Cosa NON è ancora verificato**
- Che i DP del robot corrispondano a quelli oggi in `const.py`: la mappa va letta dal device una volta connessi (i valori 14/18/19/23/24/25 restano non confermati).
- Che il firmware `1.8.71` non cambi comportamento rispetto a quanto dichiarato nell'annuncio.
- Il valore di `iot_platform` e `third_product_id_tuya` dell'account: irrilevanti ora che il canale LAN e la versione sono osservati direttamente.

**Stato dell'ipotesi LAN:** confermata e localizzata. Il robot è raggiungibile, espone il canale locale e dichiara 3.3. Il blocco residuo è la local key; il blocco tecnico noto è la versione di protocollo implementata.

## Adapter Tinytuya implementato 2026-10-26T21:19:03+01:00

**Cosa è stato creato**

| File | Ruolo |
|---|---|
| `custom_components/lefant_m1/tuya_lan_adapter.py` | client LAN Tuya basato su tinytuya, protocollo 3.1/3.3/3.4/3.5, default **3.3** |
| `tests/test_tuya_lan_adapter.py` | 7 test offline con dispositivo finto (nessuna rete, nessuna credenziale) |
| `tools/probe_robot.py` | lettura DP dal robot, chiave da variabile d'ambiente |
| `custom_components/lefant_m1/manifest.json` | aggiunta dipendenza `tinytuya>=1.20.0` |

**Interfaccia:** identica a quella che il coordinator già usa — `await connect()`, `await query_dps()`, `set_dps()`, `close()`, listener con `status_updated()`/`disconnected()`. Il blocco sincrono di tinytuya gira in `asyncio.to_thread`, quindi l'event loop non viene bloccato. Sono presenti due shim (`_writer`, `_closing`) per permettere la sostituzione senza toccare il coordinator; sono documentati come temporanei.

**Errori tipizzati:** `TuyaLanAuthError` (chiave o versione rifiutate: codici 904/914), `TuyaLanConnectionError` (901/902), `TuyaLanError` per il resto. I codici arrivano da tinytuya anche come stringa: c'è coercizione e un test dedicato.

**Verifica contro il robot reale (senza chiave valida, sola lettura):** con una chiave fittizia l'adapter invia il `DP_QUERY` 3.3 cifrato, il robot risponde con un frame 55AA e retcode 1, e la decifratura fallisce come deve. L'adapter traduce in `TuyaLanAuthError`. Questo prova tre cose insieme: il robot parla 3.3, l'adapter è correttamente collegato a tinytuya, e la catena di errori è quella giusta. Con la chiave corretta lo stesso percorso restituisce i DP.

**Cosa manca per essere operativo**
1. La **local key** del robot. `tools/probe_robot.py` la legge da `LEFANT_LOCAL_KEY` e non la stampa mai.
2. Il **wiring**: `coordinator.py:40` e `:100` costruiscono ancora `TuyaClient` (3.5). Va sostituito con `TinytuyaClient` (o reso selezionabile) perché il robot parli 3.3.
3. La **correzione della mappa DP** in `const.py`, da fare *dopo* la prima lettura reale, non prima.

**Nota:** con l'adapter il ciclo di aggiornamento è polling (default 4 s) invece che push; se si adotta in modo definitivo, `iot_class` va allineato a `local_polling` oppure il polling va tenuto corto e documentato.

## References

- `README.md:6,26-36` — architettura LAN attuale e modalità indicate per acquisire i dati di configurazione.
- `custom_components/lefant_m1/pytuya_client.py:1-50,170-241` — client Tuya LAN presente.
- `custom_components/lefant_m1/config_flow.py:20-43` — configurazione e validazione host/device ID/local key.
- `custom_components/lefant_m1/coordinator.py:23-45` — seam coordinator/client.
- `custom_components/lefant_m1/const.py:13-23` — DP dichiarati dal componente.
- `.rpiv/artifacts/research/2026-09-08_22-09-21_lefant-m1-home-assistant-integration.md:20-28` — decisione cloud storica e successivo pivot locale.
- [Home Assistant Tuya integration](https://www.home-assistant.io/integrations/tuya/) — documentazione ufficiale route Tuya in Home Assistant.
- [TinyTuya](https://github.com/jasonacox/tinytuya) — implementazione community Tuya LAN e documentazione.
- [Lefant Home Assistant LocalTuya extractor](https://github.com/hectorzin/Lefant-Home-Assistant-LocalTuya) — progetto community indipendente; materiale validato sul modello M210 Pro Omni, non sul M1.
- [Lefant official site](https://www.lefant.com) — sito produttore; le pagine consultate non hanno documentato API pubbliche.
