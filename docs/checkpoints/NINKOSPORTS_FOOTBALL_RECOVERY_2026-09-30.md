# NinkoSports News — nastavak fudbala, 30. septembar 2026.

Korisnik je tražio nastavak posle prekida. Scope ostaje samo NEWS. Prevodi su i dalje privremeno ugašeni. Ne koristiti Railway AI agenta.

## Objavljena ispravka

- Produkcioni News commit: `5a82fa743c2a7661cf50fc62e319e78ed9703b24`.
- Testirani Git tree: `4f179bcd397b741fdfc4f0ffb53c19cf2fbd3859`; identičan lokalnom commit-u `ff35de9845f35112d55114119df621b45996bf74`.
- News worker deployment: `bbfbaf46-40c0-4163-8bcd-8d6b148ee98d`, SUCCESS 10:07:48 UTC.
- Polazni produkcioni commit: `958d571138f7a3cdf9d221d8206d15633cbebdc3`.

`bot/fetch_sources.py`: kada besplatni writer padne na proveri, a OpenAI fallback ne vrati nacrt zbog limita ili nedostupnosti, čuva se prvobitni razlog i evidence. Ranije se razlog pretvarao u privremeni `empty`, pa je ista odbijena vest ponovo zauzimala red sledećeg ciklusa. Postojeća korekcija i trajni cooldown sada dobijaju stvarni razlog. Uspešan plaćeni fallback i njegova sopstvena odbijanja zadržavaju postojeće ponašanje.

`bot/news_policy.py`: UEFA referentne stranice sa tabelama strelaca i zbirkom rekorda ispadaju pre AI reda. Pravilo je vezano za UEFA host, `/news/` putanju i precizan oblik naslova. Stvarna vest o oborenom rekordu, povredi najboljeg strelca ili dodeljenoj nagradi ostaje kandidat. Potvrđeni izvori:

- https://www.uefa.com/womenschampionsleague/news/025b-0ef163bc672f-4f70d38ff3af-1000--uefa-women-s-champions-league-records/
- https://www.uefa.com/womenschampionsleague/news/02a9-21a9b14a50b6-6f4a52d748c0-1000--women-s-champions-league-2026-27-top-scorer-marie-antoine/

Prvi izvor je zbirka istorijskih rekorda; drugi tabela strelaca/asistencija. U 09:50 ciklusu oba su trošila writer pokušaje, a jedan i plaćeni zahtev. Njihov datum osvežavanja nije dovoljan da ih pretvori u novu vest.

## Testovi i trošak

263 testa prošla: OpenAI budget/transport, News policy/integration, football fill/discovery i novi regresioni slučajevi. Testovi koriste lažni HTTP i SQLite, bez plaćenih poziva. Popravljen je i stari test fixture koji je ključ postavljao na legacy modul umesto u env novog metered providera; produkcioni ključ nije čitan niti menjan.

Produkcija u 10:08:07 UTC potvrđuje `cutoff_probe={daily:true,monthly:true,total:true} paid_requests=0`. Model preflight potvrđuje `gpt-6-luna`. Budžeti, dva nova plaćena zahteva po ciklusu, zabrana skupih modela i web-search alata ostaju nepromenjeni. Prevodi ostaju ugašeni.

## Provera pokrivenosti i menija

Postojeći katalog ima 86 fudbalskih takmičenja/sekcija u 33 grupe zemalja, uključujući International. Browser provera potvrđuje da Other Leagues prikazuje 86 stavki, posebne stranice liga i izbor lige. Klik na Prvu ligu Srbije prikazuje vest o Dušanu Cvetinoviću i Teleoptiku. Novi meni nije pravljen.

Javni članak `22313`, Mathis Albert, objavljen je u prethodnom redovnom ciklusu u 10:02 UTC i API ga svrstava u `football-national-teams`. Nije pogrešno smešten u Bundesligu zbog klupskog imena u izvornom naslovu.

Ovo nije tvrdnja da svih 86 sekcija već ima sveže vesti. Početna provera prvih 100 javnih fudbalskih članaka pokazuje 21 imenovanu sekciju i deset bez precizne lige; 24-časovna produkciona inventura u 09:50 imala je 76 fudbalskih članaka, dok javni listing koristi duži prozor. Nepotvrđene činjenice i datumi i dalje se odbijaju.

Mozzart HTML kandidati sa `future_publication` nisu automatski odblokirani: stvarnu vremensku zonu tih izvora nije bilo moguće potvrditi u ovom prolazu. Ne uklanjati zaštitu od budućeg datuma bez dokaza.

## Dokaz prvog produkcionog ciklusa

U 10:10:25 UTC UEFA tabela strelaca odbijena je već u source discovery-ju sa `non_article_rolling_tracker`, bez writer zahteva. Red je zatim imao 124 prihvatljiva fudbalska kandidata.

U 10:12:32 UTC objavljen je članak **22315**, „Iván Cuéllar returns to RCD Mallorca football training after head injury“. Javni API vraća `quality_ok=true`, `sport=football`, `league=spain-la-liga-2` i puni tekst. Izvorni datum objave 10:07:39 UTC ostao je sačuvan.

Dva nova plaćena pisanja u tom ciklusu koštala su ukupno **$0.00061838** po stvarnim tokenima (4.408 input, 2.588 cached input, 821 output). Jedan nacrt zadržan je kao prekratak; drugi je prošao sve gateove i objavljen. Nije podizan plaćeni limit radi veće količine vesti.

U 10:13:00 UTC produkcioni log potvrđuje popravljeno ponašanje: `paid fallback unavailable=cycle_allowance_exhausted retained_rejection=validator-unsupported-claim`. Tekst bez potvrde nije objavljen i dodatni OpenAI zahtev nije poslat. Sirovi relevantni logovi i neizmenjeni deployment identifikatori nalaze se u `football-recovery-proof-2026-09-30.json`.

## Dokaz NEWS-only scope-a

Produkcioni diff ima tačno pet datoteka:

1. `bot/fetch_sources.py`
2. `bot/news_policy.py`
3. `tests/test_news03_integration.py`
4. `tests/test_news_openai_budget.py`
5. `tests/test_news_football_cycle_recovery.py`

Nema promena u `collector/`, `app.py`, `models.py`, `taxonomy_resolver.py`, `entities.py`, `public_index.py` niti image pipeline-u. Frontend nije menjan; lokalni HEAD ostaje `b1dfcc9e9bf82083deb15c5933de545ac14019a0`.

Ponovo potvrđeni neizmenjeni servisi, oba SUCCESS na commit-u `ff091f98b6c879c85978d78df7bdcd0853b08dfb`:

- Shared API: `a6018808-ec70-44a9-8ddc-5a65b30f9c57`, od 27. septembra.
- Results worker: `25287c7e-08a8-46f8-aa3b-0d85ba6eaf53`, od 27. septembra.

Railway AI agent nije korišćen. Izmenjena je samo `NEWS_DEPLOY_REV` varijabla na postojećem News worker servisu radi puštanja testiranog commit-a.
