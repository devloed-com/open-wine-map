import json

items = json.load(open('tmp/it-consorzio-items.json'))
consorzi = {c['id']: c for c in items['consorzi']}

# --- FOUND consorzi: cid -> (organisation name, url) ---
FOUND_C = {
 'C001':("Consorzio Tutela Vini d'Abruzzo","https://www.consorzio-viniabruzzo.it/"),
 'C002':("Sannio Consorzio Tutela Vini","https://www.sannio.wine/"),
 'C003':("Consorzio di Tutela Aglianico del Vulture","https://consorzioaglianico.it/"),
 'C004':("Consorzio Barbera d'Asti e Vini del Monferrato","https://www.viniastimonferrato.it/"),
 'C005':("Consorzio Tutela Vini di Alghero DOC","https://www.algherodoc.it/"),
 'C006':("Consorzio Alta Langa","https://www.altalangadocg.com/"),
 'C007':("Consorzio Vini Alto Adige","https://www.vinialtoadige.com/"),
 'C008':("Consorzio Tutela Vini Valpolicella","https://www.consorziovalpolicella.it/"),
 'C010':("Consorzio Tutela Vino Arcole DOC","https://www.arcoledoc.com/"),
 'C011':("Consorzio per la tutela dell'Asti","https://astidocg.it/"),
 'C012':("Consorzio per la tutela dei vini DOP Atina","https://www.atinadoc.it/"),
 'C013':("VITICA - Consorzio Tutela Vini Caserta","https://www.vitica.it/"),
 'C015':("Consorzio Tutela Vini Friularo di Bagnoli","https://www.consorziovinidocbagnoli.it/"),
 'C016':("Consorzio di Tutela Barolo Barbaresco Alba Langhe e Dogliani","https://www.langhevini.it/"),
 'C017':("Consorzio Colline del Monferrato Casalese","https://vinimonferratocasalese.it/"),
 'C018':("Consorzio di Tutela Chiaretto e Bardolino","https://consorziobardolino.it/"),
 'C019':("Consorzio Valtenesi","https://www.consorziovaltenesi.it/"),
 'C020':("Istituto Marchigiano di Tutela Vini (IMT)","https://imtdoc.it/"),
 'C021':("Consorzio Vino Chianti","https://www.consorziovinochianti.it/"),
 'C022':("Consorzio di Tutela del Bianco di Pitigliano e Sovana DOC","http://www.pitiglianodoc.it/"),
 'C023':("Consorzio di Tutela dei Vini DOC Bivongi","https://www.docbivongi.it/"),
 'C024':("Consorzio Tutela Nebbioli Alto Piemonte","https://www.consnebbiolialtop.it/"),
 'C025':("Consorzio per la Tutela dei Vini Bolgheri e Bolgheri Sassicaia","https://www.bolgheridoc.com/"),
 'C026':("Consorzio Tutela Vini Oltrepo Pavese","https://www.consorziovinioltrepo.it/"),
 'C027':("Consorzio Tutela Vini DOC Bosco Eliceo","https://www.consorzioboscoeliceo.it/"),
 'C028':("Consorzio Botticino","https://www.consorziobotticino.it/"),
 'C029':("Consorzio Tutela Vini d'Acqui","https://vinidacqui.it/"),
 'C030':("Consorzio Tutela Vini DOC Breganze","https://www.breganzedoc.it/"),
 'C031':("Consorzio Tutela Vini DOC Brindisi e DOC Squinzano","https://www.vinibrindisisquinzanodoc.it/"),
 'C032':("Consorzio del vino Brunello di Montalcino","https://www.consorziobrunellodimontalcino.it/"),
 'C034':("Consorzio Tutela Vini Campi Flegrei e Ischia","https://consorzioditutelavinicampiflegreieischia.it/"),
 'C036':("Consorzio Tutela Vini DOC Caluso, Carema e Canavese","https://www.erbalucecarema.it/"),
 'C037':("Consorzio Candia dei Colli Apuani","https://candiadeicolliapuani.it/"),
 'C038':("Consorzio Tutela Denominazioni Vini Frascati","https://consorziofrascati.it/"),
 'C039':("Consorzio Montenetto","https://consorziomontenetto.it/"),
 'C041':("Consorzio di Tutela dei Vini di Carmignano","https://www.consorziovinicarmignano.it/"),
 'C042':("Consorzio di Tutela Vini DOC Castel del Monte","https://pugliasveva.it/"),
 'C043':("Consorzio di Tutela Vita Salernum Vites","https://www.consorziovinisalerno.it/"),
 'C044':("Consorzio Vini del Trentino","https://vinideltrentino.com/"),
 'C045':("Consorzio di tutela Cerasuolo di Vittoria DOCG e Vittoria DOC","https://www.cerasuolovittoria.it/"),
 'C046':("Consorzio di tutela del Cesanese del Piglio","https://www.consorziotutelacesanesedelpiglio.it/"),
 'C047':("Consorzio Vino Chianti Classico","https://www.chianticlassico.com/"),
 'C049':("Consorzio di Tutela Vini DOC Ciro e Melissa","https://www.consorzioviniciroemelissa.it/"),
 'C050':("Consorzio Vini Colli Bolognesi","https://www.collibolognesi.it/"),
 'C051':("Consorzio Vini di Romagna","https://www.consorziovinidiromagna.it/"),
 'C052':("Consorzio Tutela Vini Trasimeno","https://www.trasimenodoc.it/"),
 'C053':("Consorzio Volontario Tutela Vini DOP Colli di Parma","https://www.viniparma.it/"),
 'C054':("Consorzio Tutela Lambrusco","https://www.tutelalambrusco.it/"),
 'C055':("Consorzio Tutela Vini Colli Euganei","https://www.collieuganeidoc.com/"),
 'C056':("Consorzio Tutela Vini Friuli Colli Orientali e Ramandolo","https://www.colliorientali.com/"),
 'C057':("Consorzio Tutela Vini Colli Tortonesi","https://collitortonesi.com/"),
 'C058':("Consorzio Volontario Vino DOC San Colombano","https://www.sancolombanodoc.it/"),
 'C059':("Consorzio del Freisa di Chieri","https://www.freisadichieri.com/"),
 'C060':("Consorzio Tutela Vini Collio","https://www.collio.it/"),
 'C061':("Consorzio Tutela del Vino Conegliano Valdobbiadene Prosecco","https://www.prosecco.it/"),
 'C063':("Consorzio di Tutela dei Vini DOC Cortona","https://www.cortonavini.it/"),
 'C064':("Consorzio di Tutela Terre di Reggio Calabria","https://www.terredireggiocalabria.it/"),
 'C065':("Consorzio per la Tutela del Franciacorta","https://franciacorta.wine/"),
 'C066':("Consorzio Tutela Vini Emilia","https://www.consorzioviniemilia.it/"),
 'C067':("Consorzio Tutela Vini DOC delle Venezie","https://dellevenezie.it/"),
 'C068':("Consorzio di Tutela e Promozione dell'Ovada DOCG","https://www.ovada.eu/"),
 'C069':("Consorzio Tutela dei Vini Etna DOC","https://consorzioetnadoc.com/"),
 'C070':("Consorzio Tutela Vini Piceni","https://www.consorziovinipiceni.com/"),
 'C071':("Consorzio Tutela Vini d'Irpinia","https://consorziovinidirpinia.it/"),
 'C072':("Consorzio Tutela Vini Friuli Venezia Giulia","https://www.docfriuli.eu/"),
 'C073':("Consorzio Tutela Vini DOC Friuli Aquileia","https://www.viniaquileia.it/"),
 'C074':("Consorzio Tutela Vini DOC Friuli Grave","https://www.docfriuligrave.com/"),
 'C075':("Consorzio Tutela Vini Gambellara","https://www.consorziogambellara.com/"),
 'C076':("Consorzio Garda DOC","https://www.gardadocvino.it/"),
 'C077':("Consorzio Vini Mantovani","https://www.vinimantovani.it/"),
 'C078':("Consorzio Tutela del Gavi","https://www.consorziogavi.com/"),
 'C079':("Consorzio di Tutela Vini DOC Gioia del Colle","http://www.consorziovinigioiadelcolle.it/"),
 'C080':("Consorzio DOC Grance Senesi","https://www.docgrancesenesi.it/"),
 'C081':("Consorzio di Tutela del Vino Gravina DOP","http://www.gravinadop.it/"),
 'C082':("Consorzio Tutela Vini DOC Colli Piacentini","https://collipiacentinidoc.it/"),
 'C083':("Consorzio Tutela Vino Lessini Durello","https://www.montilessini.com/"),
 'C084':("Consorzio Vini Venezia","https://www.consorziovinivenezia.it/"),
 'C085':("Consorzio Tutela Lugana DOC","https://www.consorziolugana.it/"),
 'C086':("Consorzio Malvasia delle Lipari","https://consorziomalvasiadellelipari.it/"),
 'C087':("Consorzio Tutela Malvasia di Bosa","https://consorziotutelamalvasiadibosa.it/"),
 'C088':("Consorzio per la Tutela della Malvasia di Casorzo","https://www.malvasiadicasorzo.it/"),
 'C089':("Consorzio Tutela Vini della Maremma Toscana","https://www.consorziovinimaremma.it/"),
 'C091':("Consorzio Volontario per la Tutela del Vino Marsala","https://consorziovinomarsala.it/"),
 'C092':("Consorzio Tutela Vini Merlara DOC","https://merlara.wine/"),
 'C094':("Consorzio Tutela Vini Montecucco","https://www.consorziomontecucco.it/"),
 'C095':("Consorzio Tutela Vini Montefalco","https://www.consorziomontefalco.it/"),
 'C096':("Consorzio Vini Asolo Montello","https://www.asolomontello.it/"),
 'C097':("Consorzio Tutela Morellino di Scansano","https://www.consorziomorellino.it/"),
 'C098':("Consorzio Volontario per la Tutela dei vini Terre di Romangia","https://www.terrediromangia.it/"),
 'C100':("Consorzio del Vino Orcia","https://www.consorziovinoorcia.it/"),
 'C101':("Consorzio Tutela Vini Orvieto","https://www.orvietodoc.it/"),
 'C102':("Consorzio di tutela e valorizzazione dei vini DOC Pinerolese","https://consorziodocpinerolese.it/"),
 'C104':("Consorzio Tutela Vini Vesuvio","https://www.vesuvio.wine/"),
 'C105':("Consorzio di Tutela del Primitivo di Manduria","https://www.consorziotutelaprimitivo.com/"),
 'C106':("Consorzio di Tutela della DOC Prosecco","https://www.prosecco.wine/"),
 'C107':("Consorzio Tutela Vini Soave e Recioto di Soave","https://www.ilsoave.com/"),
 'C108':("Consorzio Tutela Roero","https://www.consorziodelroero.it/"),
 'C109':("Consorzio Roma DOC","https://consorzioromadoc.it/"),
 'C110':("Consorzio del Vino Nobile di Montepulciano","https://www.consorziovinonobile.it/"),
 'C111':("Consorzio di Tutela Vini DOP Salice Salentino","https://www.consorziosalicesalentino.it/"),
 'C112':("Consorzio del Vino Vernaccia di San Gimignano","https://vernaccia.it/"),
 'C113':("Consorzio Tutela Moscato di Scanzo","https://consorziomoscatodiscanzo.it/"),
 'C114':("Consorzio di Tutela dei Vini di Valtellina","https://www.vinidivaltellina.it/"),
 'C115':("Consorzio di Tutela Vini DOC Sicilia","https://siciliadoc.wine/"),
 'C116':("Consorzio di tutela vini DOP Suvereto e Val di Cornia","https://www.suveretowine.com/"),
 'C117':("Consorzio di Tutela DOC Tavoliere delle Puglie","https://www.tavolieredellepugliedoc.com/"),
 'C118':("Consorzio Tutela Valcalepio","https://www.valcalepio.org/"),
 'C119':("Consorzio di Tutela dei Vini Terre di Cosenza DOP","https://www.terredicosenza.it/"),
 'C120':("Consorzio Vini Terre di Pisa","https://www.viniterredipisa.com/"),
 'C121':("Consorzio Vini IGT Terre Lariane","https://www.terrelarianeigt.it/"),
 'C123':("Consorzio Tutela Vini Torgiano","https://consorziotutelavinitorgiano.it/"),
 'C124':("Consorzio Vino Toscana","https://www.consorziovinotoscana.it/"),
 'C125':("Consorzio Valdarno di Sopra DOC","https://www.valdarnodisopradoc.it/"),
 'C126':("Consorzio Vini IGT Valle Camonica","https://www.consorziovinivallecamonica.it/"),
 'C128':("Consorzio Vini Valdichiana Toscana","https://vinivaldichianatoscana.it/"),
 'C129':("Consorzio Vini Valle d'Aosta","https://www.vinivalledaosta.com/"),
 'C130':("Consorzio di Tutela del Vermentino di Gallura DOCG","https://www.vermentinogallura.wine/"),
}
NONE_C = {'C009','C014','C033','C035','C040','C048','C062','C090','C093','C099','C103','C122','C127','C131'}

# --- FOUND nameless wines: slug -> (organisation, url) ---
FOUND_W = {
 'alba':("Consorzio di Tutela Barolo Barbaresco Alba Langhe e Dogliani","https://www.langhevini.it/"),
 'alpi-retiche':("Consorzio di Tutela dei Vini di Valtellina","https://www.vinidivaltellina.it/"),
 'alto-mincio':("Consorzio Vini Mantovani","https://www.vinimantovani.it/"),
 'asolo-montello':("Consorzio Vini Asolo Montello","https://www.asolomontello.it/"),
 'asolo-prosecco':("Consorzio Vini Asolo Montello","https://www.asolomontello.it/"),
 'barco-reale-di-carmignano':("Consorzio di Tutela dei Vini di Carmignano","https://www.consorziovinicarmignano.it/"),
 'barletta':("Consorzio per la Tutela del Vino DOC Barletta","https://consorziobarlettadoc.wordpress.com/"),
 'bergamasca':("Consorzio Tutela Valcalepio","https://www.valcalepio.org/"),
 'casteggio':("Consorzio Tutela Vini Oltrepo Pavese","https://www.consorziovinioltrepo.it/"),
 'catalanesca-del-monte-somma':("Consorzio Tutela Vini Vesuvio","https://www.vesuvio.wine/"),
 'castelfranco-emilia':("Consorzio Tutela Lambrusco","https://www.tutelalambrusco.it/"),
 'bianco-del-sillaro':("Consorzio Vini di Romagna","https://www.consorziovinidiromagna.it/"),
 'carso':("Associazione Viticoltori del Carso - Kras","https://www.carsovinokras.it/"),
 'casauria':("Consorzio Tutela Vini d'Abruzzo","https://www.consorzio-viniabruzzo.it/"),
 'ciro-classico':("Consorzio di Tutela Vini DOC Ciro e Melissa","https://www.consorzioviniciroemelissa.it/"),
 'colli-bolognesi-pignoletto':("Consorzio Vini Colli Bolognesi","https://www.collibolognesi.it/"),
 'colli-piacentini':("Consorzio Tutela Vini DOC Colli Piacentini","https://collipiacentinidoc.it/"),
 'colli-romagna-centrale':("Consorzio Vini di Romagna","https://www.consorziovinidiromagna.it/"),
 'colli-martani':("Consorzio Tutela Vini Colli Martani","https://www.umbriatopwines.it/en/denominations-and-consortiums/"),
 'colli-del-sangro':("Consorzio Tutela Vini d'Abruzzo","https://www.consorzio-viniabruzzo.it/"),
 'colli-aprutini':("Consorzio Tutela Vini d'Abruzzo","https://www.consorzio-viniabruzzo.it/"),
 'colline-teramane-montepulciano-dabruzzo':("Consorzio di Tutela Vini Colline Teramane DOCG","https://collineteramane.com/"),
 'custoza':("Consorzio Tutela Vino Custoza DOC","https://custoza.wine/"),
 'colli-di-conegliano':("Consorzio Tutela Vini Colli di Conegliano DOCG","http://www.colliconegliano.it/"),
 'colline-saluzzesi':("Consorzio di Tutela Vini DOC Colline Saluzzesi","http://www.collinesaluzzesi.com/"),
 'corti-benedettine-del-padovano':("Consorzio Tutela Vini Corti Benedettine del Padovano","https://www.cortibenedettine.it/"),
 'costa-d-amalfi':("Consorzio di Tutela Vita Salernum Vites","https://www.consorziovinisalerno.it/"),
 'elba':("Consorzio di Tutela dei Vini dell'Elba","http://www.aleaticoelba.it/"),
 'elba-aleatico-passito':("Consorzio di Tutela dei Vini dell'Elba","http://www.aleaticoelba.it/"),
 'emilia-romagna':("Consorzio Tutela Vini Emilia","https://www.consorzioviniemilia.it/"),
 'faro':("Consorzio di Tutela Vino Faro DOC","https://www.consorzioditutelavinofarodoc.it/"),
 'friuli-isonzo':("UNI.DOC FVG - Unione dei Consorzi Vini DOC del Friuli Venezia Giulia","https://www.unidocfvg.it/"),
 'friuli-annia':("UNI.DOC FVG - Unione dei Consorzi Vini DOC del Friuli Venezia Giulia","https://www.unidocfvg.it/"),
 'friuli-latisana':("UNI.DOC FVG - Unione dei Consorzi Vini DOC del Friuli Venezia Giulia","https://www.unidocfvg.it/"),
 'greco-di-bianco':("Consorzio Greco di Bianco DOP","https://www.grecodibianco.it/"),
 'grignolino-del-monferrato-casalese':("Consorzio Colline del Monferrato Casalese","https://vinimonferratocasalese.it/"),
 'i-terreni-di-sanseverino':("Istituto Marchigiano di Tutela Vini (IMT)","https://imtdoc.it/"),
 'mamertino':("Consorzio di Tutela del Mamertino DOC","https://www.mamertinodoc.com/"),
 'monreale':("Consorzio di Tutela Vino DOC Monreale","https://consorzio.docmonreale.com/"),
 'montenetto-di-brescia':("Consorzio Montenetto","https://consorziomontenetto.it/"),
 'montescudaio':("Consorzio Vino Montescudaio DOC","https://www.consorziovinomontescudaiodoc.it/"),
 'monti-lessini':("Consorzio Tutela Vino Lessini Durello","https://www.montilessini.com/"),
 'ortrugo-dei-colli-piacentini':("Consorzio Tutela Vini DOC Colli Piacentini","https://collipiacentinidoc.it/"),
 'pantelleria':("Consorzio Volontario per la Tutela dei Vini DOC dell'Isola di Pantelleria","https://www.vinipantelleriadoc.it/"),
 'provincia-di-pavia':("Consorzio Tutela Vini Oltrepo Pavese","https://www.consorziovinioltrepo.it/"),
 'rimini':("Consorzio Vini di Romagna","https://www.consorziovinidiromagna.it/"),
 'riviera-del-garda-classico':("Consorzio Valtenesi","https://www.consorziovaltenesi.it/"),
 'ronchi-di-brescia':("Consorzio Botticino","https://www.consorziobotticino.it/"),
 'sabbioneta':("Consorzio Vini Mantovani","https://www.vinimantovani.it/"),
 'salaparuta':("Consorzio Salaparuta","https://www.vinidocsalaparuta.it/"),
 'salento':("Consorzio di Tutela Vini DOP Salice Salentino","https://www.consorziosalicesalentino.it/"),
 'soave':("Consorzio Tutela Vini Soave e Recioto di Soave","https://www.ilsoave.com/"),
 'terre-aquilane':("Consorzio Tutela Vini d'Abruzzo","https://www.consorzio-viniabruzzo.it/"),
 'terre-tollesi':("Consorzio di Tutela Tullum DOCG","https://tullum.it/"),
 'terre-dell-alta-val-d-agri':("Consorzio di Tutela e Valorizzazione della DOC Terre dell'Alta Val d'Agri","https://www.terredellaltavaldagri.it/"),
 'terre-di-casole':("Consorzio Terre di Casole","https://www.consorzioterredicasole.com/"),
 'valsusa':("Consorzio per la Tutela e Valorizzazione dei Vini DOC Valsusa","https://www.consorziovalsusadoc.com/"),
 'valtenesi':("Consorzio Valtenesi","https://www.consorziovaltenesi.it/"),
 'venezia':("Consorzio Vini Venezia","https://www.consorziovinivenezia.it/"),
 'vin-santo-di-carmignano':("Consorzio di Tutela dei Vini di Carmignano","https://www.consorziovinicarmignano.it/"),
}
UNREACHABLE_W = {'montecarlo':"http://www.promontecarlo.it/consorzio_vini_doc.html (HTTP 403)"}

# build by_slug additions
additions = {}
covered=set()
for cid,(name,url) in FOUND_C.items():
    for w in consorzi[cid]['wines']:
        additions[w['slug']] = {"url":url,"label":name}
        covered.add(w['slug'])
for slug,(name,url) in FOUND_W.items():
    additions[slug] = {"url":url,"label":name}
    covered.add(slug)

# wines with NO link
no_link=[]
for cid in NONE_C:
    for w in consorzi[cid]['wines']:
        no_link.append((w['slug'],w['name'],w['kind'],'consorzio exists but no website / no consorzio'))
for w in items['nameless_wines']:
    if w['slug'] not in covered and w['slug'] not in UNREACHABLE_W:
        no_link.append((w['slug'],w['name'],w['kind'],'no consorzio found'))
for slug,note in UNREACHABLE_W.items():
    w=[x for x in items['nameless_wines'] if x['slug']==slug][0]
    no_link.append((slug,w['name'],w['kind'],'UNREACHABLE: '+note))

total=531
print('=== COVERAGE ===')
print(f'consorzi FOUND: {len(FOUND_C)} / 131   (NONE: {len(NONE_C)})')
print(f'nameless wines FOUND: {len(FOUND_W)} / 224')
print(f'appellations that get a card link: {len(covered)} / {total}  ({100*len(covered)//total}%)')
print(f'appellations with no link: {len(no_link)}')
json.dump(additions, open('tmp/it-consorzio-staged-additions.json','w'),
          ensure_ascii=False, indent=2, sort_keys=True)
json.dump([{'slug':s,'name':n,'kind':k,'note':note} for s,n,k,note in sorted(no_link)],
          open('tmp/it-consorzio-no-link.json','w'), ensure_ascii=False, indent=2)
print()
print('staged ->  tmp/it-consorzio-staged-additions.json  (', len(additions),'slug entries )')
print('no-link ->  tmp/it-consorzio-no-link.json  (', len(no_link),'wines )')
