# Case 04: Tool selection and arguments

## Task

The input is one message a user sends to a work assistant. The assistant has eight functions
(definitions below). It must call **exactly one** function with the correct arguments, or call **no
function** and answer in plain text when none of them applies. Functions are never executed; only the
call (name and arguments) is scored.

Reference date: **Tuesday 17 November 2026**. The prompt states it. All relative dates resolve
against it (rules below).

## Functions (main set)

Types in brackets are the scoring types defined under "Normalisation". `*` = required.

| Function | Use it for | Arguments |
| --- | --- | --- |
| `create_event` | Something that happens at a specific clock time: meeting, appointment, scheduled call, blocked time | `title`* [text], `date`* [date], `start_time`* [time], `duration_minutes` [int], `location` [city], `attendees` [names: array of full names of the other people] |
| `create_task` | A to-do with a due date and no clock time | `title`* [text], `due_date`* [date], `priority` [enum low/normal/high, default normal], `assignee` [name] |
| `find_contact` | Look up a person's contact details | `name`* [name], `company` [company] |
| `send_email` | Send an email | `to`* [email], `subject`* [text], `cc` [email], `body` [free] |
| `log_call` | Record a phone call that has already happened | `contact_name`* [name], `call_date`* [date], `outcome`* [enum connected/voicemail/no_answer], `duration_minutes` [int], `notes` [free] |
| `search_docs` | Search the company's internal documents | `query`* [text], `max_results` [int, default 10] |
| `get_weather` | Weather for a city, now or on a date | `location`* [city], `date` [date], `units` [enum celsius/fahrenheit, default celsius] |
| `convert_currency` | Convert an amount between currencies, at the current or a historical rate | `amount`* [number], `from_currency`* [code], `to_currency`* [code], `date` [date] |

## Shift set

Two functions are renamed and get reworded descriptions (same parameters, same meaning):
`create_task` -> `add_todo`, `search_docs` -> `query_knowledge_base`. The expected function name is the
new name. Shift requests are written in Swedish; argument values for quoted titles, subjects and search
phrases stay in Swedish exactly as written. Tool definitions stay in English. Shift items use an unseen
company list.

## Choosing the function

1. **Clock time decides event vs task.** If the request gives a clock time for the thing, it is
   `create_event`. A to-do with a day but no clock time is `create_task` (`add_todo`), even if the
   user says "schedule", "plan" or "pencil in".
2. **Past call vs future call.** A call that already happened is `log_call`. A call planned for a
   future date and time is `create_event` (the other person goes in `attendees`).
3. **No function applies** (general questions, writing help, small talk, actions no function covers
   such as booking flights or paying invoices, or questions *about* a topic such as how exchange rates
   work): call nothing and reply in text. Any call is a false call.
4. Exactly one call. Two or more calls fail, even if one of them is right.

## Choosing argument values

- Quoted titles, subjects and search phrases are copied exactly, without the quote marks.
- Required arguments are always filled from the request.
- **Optional arguments are filled only when the request gives them.** An optional argument the
  request does not give must be left out (or null / empty). Exception: an optional argument sent with
  its documented default value (`priority` normal, `max_results` 10, `units` celsius) is tolerated.
  Free arguments (`body`, `notes`) are never scored.
- `get_weather` with no date in the request: leave `date` out ("now", "right now" means no date).
- `convert_currency` with no rate date: leave `date` out.
- Currencies are ISO 4217 codes: euro(s)/€ = EUR, US dollars/dollars/$ = USD, pounds/£ = GBP,
  Swedish kronor = SEK (in Swedish requests plain "kronor"/"kr" = SEK), Norwegian kroner = NOK,
  Danish kroner = DKK, Swiss francs = CHF, yen/¥ = JPY.
- Amounts are numbers: "1,250.50" = 1250.5; Swedish "1 250,50" = 1250.5.
- Durations are minutes: "half an hour" = 30, "an hour" = 60, "an hour and a half" = 90,
  "two hours" = 120.
- Priority words: "urgent" or "high priority" = high; "low priority" = low.
- Call outcomes: the user spoke with / talked to / reached the person = connected; left a voicemail =
  voicemail; no answer / didn't pick up = no_answer.
- `attendees` lists only the other people named for the event, as full names; never the user.

### Selection rules when several candidate values are given

- **M1 Last correction wins.** If the user states a value and then corrects or changes it ("Thursday,
  no wait, Friday"), use the final value.
- **M2 Work address wins.** If a recipient has several email addresses, use the address at a company
  domain, never a personal webmail address (gmail.com, outlook.com, hotmail.com, icloud.com),
  whatever the order.

## Dates and times

Dates are output as `YYYY-MM-DD`, times as 24-hour `HH:MM`. Today = Tuesday 2026-11-17. Weeks run
Monday to Sunday; this week is 16-22 Nov, next week 23-29 Nov, last week 9-15 Nov.

| Expression (English / Swedish) | Meaning | Example |
| --- | --- | --- |
| tomorrow / i morgon, imorgon | +1 day | 2026-11-18 |
| the day after tomorrow / i övermorgon | +2 days | 2026-11-19 |
| yesterday / i går, igår | -1 day | 2026-11-16 |
| in N days / om N dagar | +N days | in three days = 2026-11-20 |
| N days ago / för N dagar sedan | -N days | |
| in a week / om en vecka; in two weeks / om två veckor | +7 / +14 days | 2026-11-24 / 2026-12-01 |
| a week ago / för en vecka sedan | -7 days | 2026-11-10 |
| on <weekday>, this <weekday> / på <veckodag> | the first such day after today | on Friday = 2026-11-20, on Monday = 2026-11-23 |
| next <weekday> / nästa <veckodag> | that weekday in next week (23-29 Nov) | next Tuesday = 2026-11-24, next Friday = 2026-11-27 |
| last <weekday> / i <veckodag>s (i fredags) | that weekday in last week (9-15 Nov) | last Friday = 2026-11-13 |
| a date without a year | the next such date on or after today for future actions (events, tasks, weather); the most recent such date before today for past things (logged calls, historical rates) | "5 January" for a task = 2027-01-05 |

Times: "2:30 pm" = 14:30, "2pm" = 14:00, Swedish "kl. 14.30" = 14:30, "klockan 9" = 09:00.

## Output contract

A response is either one function call whose arguments are a JSON object, or a plain-text reply with
no call. Invalid: two or more calls, arguments that are not a JSON object, an unknown function name.

## Normalisation (applied to both expected and returned values)

- **date**: `YYYY-MM-DD`; also accepted: `YYYY/MM/DD`, an ISO date-time (date part taken),
  "24 November 2026", "November 24, 2026". Anything else is wrong.
- **time**: `H:MM`, `HH:MM` or `HH:MM:00`, 24-hour, compared as `HH:MM`.
- **int**: an integer, a float with no fraction, or a string of digits.
- **number**: an int or float, or a numeric string (commas and spaces removed); compared with a
  tolerance of 0.001.
- **code**: trimmed, upper-cased.
- **enum**: trimmed, case-insensitive.
- **email**: trimmed, case-insensitive, a leading `mailto:` removed.
- **name**: case-insensitive, diacritics ignored, whitespace collapsed.
- **names**: a JSON array of names, compared as a set. A plain string is wrong.
- **city**: as name, using only the part before the first comma ("Oslo, Norway" = "Oslo").
- **company**: as name, with a trailing legal suffix (AB, GmbH, AG, Ltd, PLC, Inc., LLC, Corp., AS,
  ASA, Oy, Oyj, A/S, ApS, SA, SAS, B.V., N.V.) removed.
- **text**: case-insensitive, surrounding whitespace and quote marks removed, trailing `.`, `!`, `?`
  removed, whitespace collapsed. Otherwise exact.
- **free**: not scored.

## Pass rule

- Tool item: exactly one call, to the right function, every expected argument (all required ones plus
  the optional ones the request gives) equal after normalisation, and no other non-free argument with a
  non-empty value other than its documented default.
- No-tool item: no function call. The text is not scored.

Secondary scores: tool-name accuracy (right function, or no call on no-tool items), argument accuracy
(share of expected arguments right, on tool items where the function is right), false-call rate on
no-tool items, missed-call rate on tool items.

## Failure categories

`wrong_tool`, `missed_call`, `false_call`, `multiple_calls`, `wrong_value`, `date_resolution` (a date
argument is wrong), `missing_arg`, `extra_arg`, `bad_arguments` (not a JSON object or unknown function),
`nonanswer` (no call and an empty reply, a question or a refusal on a tool item), `other`.

## Slices

- `plain`: any function, absolute dates, a random subset of optional arguments.
- `relative_dates`: the date argument is a relative expression from the table.
- `optional_omitted`: no optional argument is given; the request is minimal.
- `lookalike_tools`: `create_event` vs `create_task` (clock time or not, with misleading wording), and
  `create_event` (future call) vs `log_call` (past call).
- `multi_candidate`: two candidate values for one argument, settled by M1 or M2.
- `no_tool`: no function applies (15% of items), including near misses that mention a tool's topic.
