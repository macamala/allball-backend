# NinkoSports News — OpenAI i prevodi, 30. septembar 2026.

**Konačna odluka korisnika, 19:45 Sydney:** prevodi su privremeno isključeni. Sajt je na engleskom, bez birača jezika na desktopu, mobilnom meniju i profilu. Čitalac može koristiti prevod svog pregledača. Postojeći prevodi i kod nisu obrisani. OpenAI pisanje vesti ostaje uključeno sa svim budžetskim zaštitama.

OpenAI je dodat u postojeći News lanac. Nema drugog news sistema. API ključ ostaje u postojećem News secret okruženju; nije u repozitorijumu, izveštaju ni logovima.

## Objavljene verzije

- News backend: `958d571138f7a3cdf9d221d8206d15633cbebdc3`, grana `ops/news-free-probe-20260926`; testirano stablo `1b09e8819acab8e9433d66a8ff112807f69ad6a7`.
- News worker deployment: `044664f7-f89a-4f99-ac8e-acfcf505c80e`.
- Frontend: `c2feff9c43631f7c7fc51e2f326f5549fdd70f13`, grana `master`; testirano stablo `23fdea7c45689a859e042f098329fab3f292d337`.
- Frontend deployment: `65c9e0b4-f059-45d8-869b-a521dceb3494`.

## Model i provider lanac

Autentifikovan GET /v1/models na stvarnom News API nalogu potvrdio je `gpt-6-luna` među 133 vidljiva modela. Pilot je zatim dobio 20 uspešnih HTTP odgovora ovog modela.

Za važne fudbalske vesti koristi se postojeći `football_editorial_priority` i `PRIMARY_COMPETITIONS` iz `bot/news_football_priority.py`. Ne postoji nova kopirana lista prioriteta. Luna piše prva u toj grani. Ostale vesti prvo koriste postojeći besplatni writer, a Luna je rezerva za nedostupan ili odbijen nacrt. Pisanje koristi reasoning=low; prevod reasoning=none. Svi pozivi imaju standard service tier, bez tools i bez automatskog izbora drugog modela.

Svaki nacrt prolazi postojeće provere brojeva, imena, izvora, originalnosti, jezika i nezavisnog besplatnog semantičkog validatora. Nedostupan validator ne daje dozvolu za objavu. OpenAI nema pravo da dopunjava činjenice iz memorije. Klasifikacija, routing, dedupe, lige i sportske kategorije ostaju deterministički kod. Image pipeline nije promenjen. Rezultati utakmica nisu ulaz u ovaj provider.

Pre privremenog gašenja, prevodi su koristili postojeći DeepL Free, zatim besplatni AI lanac, zatim Lunu samo za jezike koji nisu uspešno prevedeni. Već spremni ili uspešni delimični prevodi ostaju sačuvani. Sve tri grane prolaze i nezavisnu semantičku proveru. Ciljni jezici su izričito imenovani (sr=Serbian Latin, es=Spanish, itd.); validator vraća zasebnu presudu za svaki jezik. Loš španski prevod zato ne odbacuje dobar srpski. Raniji plaćeni odgovor koji je bio zadržan u grupnoj proveri može se proveriti iz keša bez novog plaćanja. Prve v15 besplatne prevode radnik ponovo proverava kroz v16; validirane gotove prevode ne ponavlja.

## Budžet i evidencija

Podešavanja samo na News servisu:

```dotenv
OPENAI_API_KEY=<postojeci-secret>
OPENAI_MODEL=gpt-6-luna
OPENAI_ENABLED=true
OPENAI_DAILY_BUDGET_USD=0.50
OPENAI_MONTHLY_BUDGET_USD=15.00
OPENAI_TOTAL_BUDGET_USD=15.00
OPENAI_EXPENSIVE_MODELS_ENABLED=false
OPENAI_WEB_SEARCH_ENABLED=false
OPENAI_ROLLOUT_MODE=production
OPENAI_PRODUCTION_APPROVED=true
OPENAI_MAX_REQUESTS_PER_CYCLE=2
OPENAI_DRY_RUN_ARTICLES=20
NEWS_TRANSLATIONS_ENABLED=0
NEWS_TRANSLATIONS_PER_CYCLE=0
NEWS_TRANSLATION_LANGUAGES_PER_ARTICLE=6
NEWS_TRANSLATION_PRIORITY_ARTICLE_IDS=
OPENAI_TRANSLATIONS_ENABLED=false
```

Frontend: `VITE_SITE_LANGUAGES_ENABLED=false`. Prethodno sačuvan srpski jezik ili profilna preferencija ne mogu ponovo uključiti prevode dok je ova opcija ugašena; stare preference ostaju sačuvane.

Dnevni i mesečni periodi računaju se u UTC. Dodatni ukupni limit od $15 čuva približno $5 od početnih $20 i kada kalendar pređe u novi mesec. Taj ukupni limit se ne resetuje automatski.

Dve nove News tabele, `news_openai_gate` i `news_openai_usage`, koriste postojeću PostgreSQL konekciju. Pre slanja se pod trajnim zaključavanjem rezerviše konzervativna maksimalna cena zahteva. Računaju se i paralelni zahtevi. Nakon poznatog odgovora rezervacija se zamenjuje procenom po stvarnim tokenima. Kod timeouta ili nepoznatog ishoda rezervacija ostaje zauzeta, a isti zahtev se automatski ne ponavlja.

Evidencija sadrži model, svrhu, jezik, ulazne/keširane/cache-write/izlazne tokene, procenu USD, vreme, source hash, article ID, status i ishod provere. Pre objave article ID još ne postoji; trajni source hash povezuje pokušaj sa člankom kada ga postojeći publisher sačuva. Idempotentnost obuhvata izvor, verziju činjenica, svrhu i jezik. Izmena prompta sama ne naplaćuje isti izvor ponovo.

Dosegnut limit zatvara samo plaćenu granu. Besplatni provideri ostaju u radu. Ni stari OpenAI legacy poziv više ne može da zaobiđe monetarni tracker.

## Pilot na 20 stvarnih članaka

Sirovi merni podaci su u `openai-pilot-2026-09-30.json`. Ovo su stvarni API tokeni iz redovnog source-ingestion toka, sa USD izračunatim po zvaničnim cenama, a ne sintetički odgovori.

| Mera | Rezultat |
|---|---:|
| Plaćene operacije | 20 |
| Duple plaćene operacije | 0 |
| Ulazni tokeni ukupno | 48.669 |
| Keširani ulazni tokeni | 23.292 |
| Cache-write tokeni | 2.588 |
| Izlazni tokeni, uključujući reasoning | 6.901 |
| Ukupna procena troška | $0.00628582 |
| Prošlo sve gateove | 9 |
| Zadržano zbog provera | 11 |
| Poslednjih pet sa konačnim podešavanjem | 5/5 prošlo |
| Trošak poslednjih pet | $0.00230481 |

Prvih pet zadržanih nacrta bilo je prekratko. Zato je dopunjeno uputstvo za zaseban puni body od približno 180–240 reči, bez ponavljanja i izmišljanja. Kasniji gateovi zadržali su dodatne brojeve, naziv koji izvor nije naveo, preveliko preklapanje sa izvorom, nepodudaranje takmičenja i izvor tipa analiza. Provere nisu olabavljene. Zatim je za pisanje uključen reasoning=low na istom Luna modelu: poslednjih pet prošlo je sve provere. Nijedan Luna tekst nije objavljen kroz dry-run granu.

Konačni mali uzorak daje oko $0.000461 po pisanju, odnosno **$0.2305 za 500 Luna pisanja dnevno** i **$6.91 za 30 dana**. To je projekcija po pet uspešnih članaka, ne obećanje prolaznosti ili količine. Prevodi i eventualni dodatni pokušaji drugih članaka nisu uključeni u ovu writer projekciju. U stvarnom smart routingu deo vesti ostaje besplatan; ukupna plaćena obrada svih svrha deli iste limite $0.50/$15.

Zvanična standardna cena po milion tokena: input $0.10, cached input $0.01, cache writes $0.125, output $0.50. Izvor: https://developers.openai.com/api/docs/models/gpt-6-luna (provereno 30.09.2026).

## Prethodno završena ispravka prevoda (sada pauzirana po nalogu korisnika)

Na stvarnom članku 22305 endpoint za srpski vraćao je `available:false, status:missing`. Navigation je imala svoje prevode, ali tekst vesti nije imao spremljen prevod. Kartice i hero naslovi takođe nisu učitavali postojeće prevode.

- Prevod sada ima ograničen deo do osam zahteva (najviše pola redovnog ciklusa) na početku ISTOG News ciklusa, pa ga pisanje ne može potpuno potisnuti. Ukupni postojeći dnevni/request limiti nisu povećani.
- Obrada bira do tri članka po ciklusu, svi nedostajući ponuđeni jezici po članku. Prijavljeni primer 22294 ima prednost, zatim članci bez srpskog. Filter izostavlja završene članke pre limita upita, pa starija arhiva može da dođe na red. Spremni jezici se ne prevode ponovo.
- Besplatni Groq JSON izlaz poštuje traženi plafon do 9.000 tokena za kompletan višejezični članak; raniji limit 2.200 mogao je da odseče odgovor. Mali zahtevi zadržavaju svoje male limite.
- Istek malog dela kvote ne označava neobrađene članke kao neuspele.
- Ispravljena je lažna blokada za `Defender Vivian`: uloga se prevodi, ali ime `Vivian` ostaje zaključano. Isto važi za eksplicitne uloge u postojećoj heuristici.
- Naslov, sažetak i body čitaoca koriste postojeći translation endpoint. News kartice, hero, SportDesk, latest/most-read, pager, inline-related i News sidebar koriste spremljene prevode.
- Najviše četiri istovremena GET zahteva za prevod, sa keširanjem i spajanjem duplikata. Klik čitaoca ne poziva plaćeni AI.
- Nedostajući prevod je jasno označen lokalizovanom porukom. Otvoreni članak proverava novi sačuvani prevod na 30 sekundi, kartice na 60 sekundi, i automatski ga prikaže bez klika. Provere prestaju za spremne prevode i pri napuštanju stranice; skriveni tab ne šalje provere. Dugme je samo opciona trenutna provera.

Prva produkciona Luna provera: 22307 i 22309 prošli sve gateove i objavljeni u redovnom News toku. Dva nova plaćena poziva koštala su $0.00085888; ledger u 09:18 UTC prikazuje 22 plaćene operacije ukupno, $0.00714470 uključujući pilot. Raniji prihvaćeni dry-run odgovori ponovo su iskorišćeni iz keša u odobrenoj produkcionoj grani bez novog plaćanja.

Produkcioni dokaz 09:41:03 UTC: članak **22294 (Raphinha)** dobio je svih šest prevoda `sr,es,de,fr,it,pt` preko Groq + nezavisnog Cloudflare validatora. Za taj članak nije korišćen OpenAI: plaćeni trošak prevoda $0. Stranica je sama prešla na srpski naslov, sažetak i puni tekst, bez klika ili reload-a. To ne znači da je cela istorijska arhiva već bila popunjena.

U 19:45 Sydney korisnik je izričito zatražio uklanjanje prevoda do kasnijeg rasta sajta. Automatski translation job je ugašen, a OpenAI `purpose=translate` ima i zasebnu zabranu pre HTTP poziva i rezervacije novca.

## Testovi i granice scope-a

Poslednji kompletan relevantni backend skup: 296 prolaznih testova. Poslednji dodatni skup: 86 fokusiranih backend testova, uključujući arhivu iza 130 već prevedenih članaka i odbijanje promene značenja u besplatnom prevodu. Frontend: prethodno 39 News/API/UI testova; potom 34 fokusirana testa sa automatskim učitavanjem prevoda. Završno gašenje provereno kroz 31 frontend test i production build, plus 49 fokusiranih backend testova. Poseban test potvrđuje da zabranjeni prevod ne šalje HTTP poziv i ne rezerviše novac, dok pisanje i dalje radi. Test interfejsa potvrđuje da ranije sačuvani srpski jezik ne vraća birač jezika niti srpski interfejs.

Budžet je testiran na konkurentnim rezervacijama, restartu, UTC prelasku dana/meseca, timeoutu, izgubljenom odgovoru, zabranjenom modelu, keširanom odgovoru, fallbacku i neispravnoj konfiguraciji. Stvarna PostgreSQL probe provera potvrdila je blokadu dnevnog, mesečnog i ukupnog limita uz nula plaćenih poziva. Limit nije dokazivan trošenjem korisnikovih $15.

Backend diff prema pre-task `dd1144ec6042c4fee466472e4927d5948c2a6c56` sadrži samo News writer/router/translation/scheduler kod i News testove. Frontend diff prema `8ee13e024b917184d479392ae88ee17d8f91069d` sadrži News prikaz i translation GET funkciju/testove, uz poslednju izričito traženu promenu birača jezika i profilnog jezičkog polja. Sportski/live-score kod i funkcije nisu menjani. U završnoj proveri 18 backend i 20 frontend zaštićenih live-score/fixture/result/standings/image putanja ostalo je identično (isti Git blob SHA); potpuni diff nema live-score izmene. Detalji i spisak su u `news-scope-proof-2026-09-30.json`.

Neizmenjeni servisi:
- Shared API: deployment `a6018808-ec70-44a9-8ddc-5a65b30f9c57`.
- Results worker: deployment `25287c7e-08a8-46f8-aa3b-0d85ba6eaf53`.
- Oba ostaju na `ff091f98b6c879c85978d78df7bdcd0853b08dfb`, deployment iz 27. septembra.
- Nisu menjane konfiguracije ni kod Live Scores, fixtures, standings ili results worker-a.
- Railway AI agent nije korišćen. Kod je rađen direktno, deployment postojećih News/News-UI izmena preko konektora.

## Ponovno uključivanje kasnije

Kod, statički rečnici i sačuvani prevodi su ostali u repozitorijumu/bazi. Za povratak funkcije potrebno je namerno uključiti frontend `VITE_SITE_LANGUAGES_ENABLED=true` i postojeći News translation job. Plaćeni prevodi imaju odvojenu zastavicu `OPENAI_TRANSLATIONS_ENABLED`; ona ostaje `false` dok korisnik ponovo ne odobri taj trošak.

## Završna vizuelna potvrda

Objavljeni frontend je proveren u istom pregledaču koji je prethodno imao izabran srpski: navigacija, naslov, sažetak i tekst su na engleskom; birača jezika više nema. Snimak: `ninkosports-news-english-20260930.jpg`.
