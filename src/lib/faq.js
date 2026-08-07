// Generates the site's FAQ entries entirely from data already verified
// elsewhere -- per-brand and per-country answers are thin wrappers around
// logic that already renders on those brands'/countries' own pages
// (see licenceSummaryText in data.js), so nothing here is a new claim.
// The handful of general questions are hand-written but restate facts
// already published on /about/ and /regulators/, not new research.
import { COUNTRY_NAMES, NON_EEA_PREFIX, licenceSummaryText, listJoin, countriesInData } from './data.js';

function brandQuestion(ex) {
  return {
    id: `brand-${ex.id}`,
    category: 'brand',
    question: `Is ${ex.brand} licensed?`,
    answer: licenceSummaryText(ex),
    href: `/exchange/${ex.id}/`,
  };
}

// Lowercase a regulator tier label for mid-sentence use, but not when it's
// an acronym like "AML" -- that should stay capitalised regardless of
// position in the sentence.
function midSentenceLabel(rawLabel) {
  const firstWord = rawLabel.split(/[\s-]/)[0];
  const isAcronym = firstWord.length > 1 && firstWord === firstWord.toUpperCase();
  return isAcronym ? rawLabel : rawLabel.charAt(0).toLowerCase() + rawLabel.slice(1);
}

function countryQuestion(cc, exchanges, regulatorDetails) {
  const name = COUNTRY_NAMES[cc] ?? cc;
  const count = exchanges.filter((ex) => ex.countries?.[cc]).length;
  const isNonEEA = cc in NON_EEA_PREFIX;
  let answer;
  if (isNonEEA) {
    // A jurisdiction can carry more than one tracked regime under the same
    // country page -- e.g. US covers both federal FinCEN (code: US) and
    // the separate NY DFS state licence (code: US-NY). Mention every one,
    // not just whichever regulator_details.yaml entry has an exact code
    // match, or the FAQ answer undersells what the country page itself
    // actually explains.
    const details = regulatorDetails.filter((d) => d.code === cc || d.code.startsWith(`${cc}-`));
    if (details.length === 0) {
      answer = `${count} exchange${count === 1 ? '' : 's'} in our register hold a tracked status covering ${name}.`;
    } else {
      const parts = details.map((d) => {
        const label = midSentenceLabel(d.tier_label ?? 'tracked status');
        const article = /^[aeiou]/i.test(label) ? 'an' : 'a';
        return `${article} ${label} via ${d.name}`;
      });
      answer = `${count} exchange${count === 1 ? '' : 's'} in our register hold ${listJoin(parts)} covering ${name}. See our ${name} page for which entity, and since when.`;
    }
  } else {
    answer = `${count} exchange${count === 1 ? '' : 's'} in our register hold an EU MiCA authorisation covering ${name}, per the official ESMA interim MiCA register. A MiCA authorisation is granted by one national regulator and passports across the whole EU/EEA, so most of these brands are not based in ${name} itself.`;
  }
  return {
    id: `country-${cc.toLowerCase()}`,
    category: 'country',
    question: `Which crypto exchanges are ${isNonEEA ? 'licensed or registered' : 'licensed'} in ${name}?`,
    answer,
    href: `/${cc.toLowerCase()}/`,
  };
}

// Hand-written, but every answer restates a distinction already published
// and sourced elsewhere on the site -- see /about/ and /regulators/ for
// the primary-source backing behind each of these.
const GENERAL_QUESTIONS = [
  {
    id: 'general-licensed-vs-registered',
    question: "What's the difference between a licensed and a registered crypto exchange?",
    answer: "A licence (MiCA, Dubai VARA, Singapore MAS, Hong Kong SFC, Japan FSA, Malaysia SC, Gibraltar GFSC, or a New York DFS BitLicense) means the regulator assessed the business itself -- capital, fitness of directors, custody arrangements -- before approving it. A registration (UK FCA MLR, Canada FINTRAC, US FinCEN MSB, South Korea FIU) is anti-money-laundering supervision only: the regulator has not evaluated or approved the firm's products or conduct.",
    href: '/regulators/',
  },
  {
    id: 'general-mica',
    question: 'What does MiCA authorisation mean?',
    answer: "MiCA (Markets in Crypto-Assets Regulation) is the EU's crypto-specific licensing regime. An exchange applies to one national regulator in its home EU/EEA state; once authorised there, that single licence passports across the whole EU/EEA. It's a genuine, assessed licence, not an AML-only registration.",
    href: '/regulators/',
  },
  {
    id: 'general-fincen',
    question: 'Is US FinCEN registration the same as a crypto licence?',
    answer: "No. FinCEN Money Services Business registration is federal anti-money-laundering supervision under the Bank Secrecy Act -- it does not mean the exchange's products or conduct have been assessed. FinCEN's own register also has a documented fraud problem: it warns that scammers register shell companies under recognisable brand names to appear \"FinCEN approved.\"",
    href: '/us/',
  },
  {
    id: 'general-bitlicense',
    question: 'What is a BitLicense?',
    answer: "A BitLicense is a Virtual Currency License issued by the New York State Department of Financial Services (NYDFS) under 23 NYCRR Part 200 -- a genuine, state-chartered licence, separate from federal FinCEN registration. It's the only US state with both a dedicated crypto-specific licence and a public, checkable list of who holds one.",
    href: '/us/',
  },
  {
    id: 'general-not-listed',
    question: "What does it mean if an exchange isn't on this register?",
    answer: "Either it holds no licence or registration we could independently verify in any of the jurisdictions we track, or we simply haven't added it yet -- absence here is not itself an accusation. You can check directly against the primary regulator source linked on each country page, or submit the exchange's details for us to verify.",
    href: '/submit/',
  },
  {
    id: 'general-provider-vs-exchange',
    question: "What's the difference between an Exchange and a Technology Provider on this site?",
    answer: 'An Exchange entry is a licence or registration record from an official regulator. A Technology Provider Profile is editorial content covering apps or platforms that are NOT independently licensed themselves, but rely on a licensed custodian or execution partner to actually hold and execute customer assets -- explicitly not part of the register.',
    href: '/providers/',
  },
  {
    id: 'general-who-holds-crypto',
    question: 'Who actually holds my crypto if the app I use is not itself licensed?',
    answer: "It depends on the app's actual business model, not its marketing. Some unlicensed-looking apps are a technology layer on top of a licensed custodian or execution partner -- see our Providers section for named examples with the partner relationship independently verified. Others may hold assets themselves with no licence at all, which is exactly the kind of gap this register exists to surface.",
    href: '/providers/',
  },
  {
    id: 'general-verified-facts-badge',
    question: 'What does a "Verified Facts" badge mean on a Provider Profile?',
    answer: "It means every regulatory claim on that profile has been checked against a primary source by us, not just repeated from the company's own disclosure. It's free and editorial -- it never depends on payment or on the company having engaged with us at all.",
    href: '/providers/',
  },
  {
    id: 'general-claimed-profile-badge',
    question: 'What does a "Claimed Profile" badge mean?',
    answer: 'It means the company has proven it controls that profile, via a confirmed email address and a real backlink from their own website -- required before we activate a working link to their site. It says nothing about whether the regulatory facts on the profile are verified; that\'s a separate "Verified Facts" badge.',
    href: '/providers/',
  },
  {
    id: 'general-how-often-updated',
    question: 'How often is this register updated?',
    answer: 'Most jurisdictions sync automatically against the live official regulator register on a weekly schedule, with changes opened as a pull request for human review before merging -- never auto-published. A couple of sources sit behind bot protection and are refreshed manually instead; each country page states its own source and last-checked date.',
    href: '/changelog/',
  },
];

export function buildFaqEntries(exchanges, regulatorDetails) {
  const brandEntries = exchanges.map(brandQuestion);
  const countryEntries = countriesInData(exchanges).map((cc) => countryQuestion(cc, exchanges, regulatorDetails));
  const generalEntries = GENERAL_QUESTIONS.map((q) => ({ ...q, category: 'general' }));
  return [...generalEntries, ...countryEntries, ...brandEntries];
}
