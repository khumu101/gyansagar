# Gyansagar — Django Full Project (Frontend + Backend)

Nursery bata PhD samma: classes, programs (faculty), subjects, chapters, notes/books/videos upload,
login/signup, ra sidebar ko sabai pages — sabai backend ma kaam garchhan.

## Kasari kaam garcha (flow)

1. **Admin** le Class → Faculty/Program → Subject → Chapter banauchha (Admin panel)
2. **Admin / Teacher** le **Resources → Add** ma: *Class → Faculty → Subject → Chapter* choose garera note/book/video/old question upload garcha
   (file upload ya link). Dropdown haru ek-arka lai filter garchhan.
3. **Student** le tyo class (ya faculty) ma gayepachi **tei class bhitrai** subject-wise notes dekhcha — left sidebar chaindaina.
   Subject ma gayo bhane Notes/Books/Question Banks tala nai dekhcha, tab ma pani.
4. File open/download garna **login** chahincha (signup free).

## Features

**Accounts** (`/accounts/...`) — Signup (auto-login), Login (username **ya** email), Logout, Profile, Change/Forgot password.
Password rule simple: **minimum 6 characters** matra (`PASSWORD_MIN_LENGTH` bata badlana milcha).
Galat password 5 patak → 15 min lock.

**Inside a class / program / subject page**
- Sidebar hidden; notes & study material subject-wise (degree ma faculty › semester › subject) — `?kind=` chips le Notes/Books/Videos filter
- Subject page: syllabus + uploaded Notes/Books/Question Banks/Worksheets, 11 tabs, "Start Learning ›" = tei chapter ko notes, "Download Syllabus" (.txt)

**Left sidebar (sabai kaam garchhan)**
| Link | Ke garcha |
|---|---|
| Home | homepage |
| Courses | sabai class + program catalogue |
| Notes / Old Questions / Books / Videos / Live Classes / Quizzes / Games | tyo type ko sabai upload; **Class → Faculty → Subject** filter + search + pagination |
| Syllabus | class/program choose garera chapter-wise syllabus |
| AI Tutor | study question sodhne (ANTHROPIC_API_KEY halyo bhane AI answer; nabhaye related notes/chapters suggest garcha) |
| Schools | schools directory (search/filter) |
| Study Tools | Pomodoro timer, marks→percentage, GPA calculator, exam countdown |
| Community | discussion posts + replies (login chahincha), delete/moderation |
| Blogs | blog posts |
| Scholarships / Careers | opportunities list (open/closed, deadline, apply link) |
| More | sabai pages ko hub + Contact form |

Home ko "Popular Categories" cards pani links bhayeka chhan.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo          # basic demo
python manage.py seed_full          # Nursery–Class 12 subjects + BSc CSIT 8 semesters (safe to re-run)
python manage.py seed_portal        # 3 starter blog posts
python manage.py createsuperuser
python manage.py runserver
```

Site: http://127.0.0.1:8000/ · Admin: http://127.0.0.1:8000/admin/
(Purano `db.sqlite3` ma pani `migrate` safe chha.)

## Admin ma content halne

| Kaam | Kaha |
|---|---|
| Class / Program / Subject / Chapter | Admin → Levels / Programs / Subjects (chapters inline) — slug khali choddina milcha |
| **Note / Book / Video / Old question upload** | Admin → **Resources → Add** → Class → Faculty → Subject → (Chapter) → type → file/link |
| Live class | type = Live Classes → join link + start time |
| Hide | "Is published" untick, ya list ma "Hide selected" |
| Schools / Scholarships / Careers / Blogs | Admin → Portal section |
| Community moderation | Admin → Posts / Comments (hide ya delete) |
| Contact messages | Admin → Contact messages |

Files: pdf, doc(x), ppt(x), xls(x), txt, csv, zip, jpg/png/gif/webp, mp4/webm, mp3 — max 100 MB (`RESOURCE_MAX_UPLOAD_MB`).
Video ko lagi YouTube link recommend.

**Teacher account:** Admin → Users → *Staff status* tick + Group **Teachers** → upload garna milcha. Signup garne le aafai teacher banna sakdaina.

## Settings (environment variables)

Local ma kei chahidaina. Server ma:

| Variable | Kaam |
|---|---|
| `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | production |
| `DJANGO_BEHIND_PROXY=1` | proxy pachadi HTTPS |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT` | real email (nabhaye terminal ma print) |
| `ANTHROPIC_API_KEY` | AI Tutor on garne |
| `AI_TUTOR_MODEL` (default `claude-haiku-5-5`), `AI_TUTOR_DAILY_LIMIT` (20), `AI_TUTOR_MAX_TOKENS` | AI Tutor tuning — model naam tapai ko key le support garne hunuparcha |
| `PASSWORD_MIN_LENGTH` (6), `SIGNUP_AUTO_LOGIN`, `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `RESOURCE_MAX_UPLOAD_MB` | misc |

## Tests

```bash
python manage.py test      # 97 tests
```

## Frontend ma ke change bhayo

- `style.css`, `app.js`, `search_results.html` — same
- `base.html`: sidebar links ab real (context bata), class pages ma sidebar hide, Login/Sign Up real
- `home.html`: login card + category cards links
- `level_detail.html`, `program_detail.html`, `subject_detail.html`: notes panel include + `#` links wired
- **Naya:** browse/courses/syllabus pages, `extras.css`, account + portal pages

## Known limits

- Quiz auto-grading, progress tracking, payments chhaina (Quizzes tab ma quiz file/link upload hunchha)
- Right-side widgets (Daily Goal, Top Learners, Announcements, Your Progress) static design nai
- Seed ko CSIT subject/chapter names demo ho — official TU syllabus sanga verify garnu. Schools/Scholarships/Careers real facts ho, tyasaile seed gareko chhaina
- AI Tutor: real API call tapai ko key sanga test garnu parcha (yaha mocked tests matra)
- Login lock cache per-process (multi-server ma Redis cache)


## Production (Docker, PostgreSQL, backups, Sentry)

Everything for a real server is included: `Dockerfile`, `docker-compose.yml` (web + PostgreSQL + Redis + nginx + daily backups),
`deploy/nginx/gyansagar.conf`, `.env.example`, GitHub Actions CI and **[DEPLOY.md](DEPLOY.md)** with step-by-step instructions.

Quick version: `cp .env.example .env` → edit → `docker compose up -d --build`.

Useful commands:

| Command | What it does |
|---|---|
| `python manage.py backup [--keep N] [--dir D] [--no-media]` | database dump + uploads archive, rotates old ones |
| `python manage.py restore FILE --yes [--media FILE]` | restores a backup (overwrites current data) |
| `python manage.py ensure_superuser` | creates the admin from `DJANGO_SUPERUSER_*` env vars if missing |
| `GET /healthz/`, `GET /readyz/` | liveness / readiness probes for uptime monitors |


## Phase 2 features

| Feature | Where |
|---|---|
| **E-mail verification** (signed links, 72 h; banner + resend; optional gate `REQUIRE_VERIFIED_EMAIL=1`) | sign-up, profile |
| **Report a file** (🚩 on every file; N reports hide it; admin queue with *resolve / hide / restore*) | file rows, Admin → Resource reports |
| **Search** now also finds files by title/description | top search bar |
| **Practice tests** (MCQ, graded on the server, review with explanations, pass mark) | `/learn/quizzes/`, create in Admin → Quizzes |
| **Assignments** (text/file submission, late flag, teacher grading with marks + feedback, private downloads) | `/learn/assignments/`, `/learn/grading/` |
| **My Learning** dashboard for students | `/learn/` |
| **Site statistics** for staff (users, downloads, top files/subjects, test results, open reports) | `/dashboard/` |

Teachers: set role = Teacher + Staff + group *Teachers*; they then create quizzes/assignments in the admin and only see their own.
Not included yet: online payments (eSewa / Khalti need your merchant account keys).


## Previews, text notes, any format, Google login

* **Preview:** PDF / images / video / audio / `.txt` open inside the site (`/resource/<id>/`), with separate Download.
* **Text notes:** the admin "Content" box lets teachers type old questions or notes directly; no file needed.
* **Any format:** everything is accepted except programs/scripts/web pages (`RESOURCE_BLOCKED_EXTENSIONS` in settings).
* **Continue with Google:** set `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` (setup steps in DEPLOY.md). Without them the button is hidden.
