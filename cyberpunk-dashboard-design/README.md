# Lakshya - Cyberpunk Dashboard UI

This is the Next.js frontend for the Lakshya Target Scoring System, styled with a cyberpunk/tactical theme.

## Prerequisites

- Node.js 18+ installed
- pnpm (or npm/yarn)
- Flask backend running on `http://127.0.0.1:5000`

## Setup

1. Navigate to the cyberpunk-dashboard-design directory:
```bash
cd cyberpunk-dashboard-design
```

2. Install dependencies:
```bash
pnpm install
# or
npm install
```

3. Start the development server:
```bash
pnpm dev
# or
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Running with Flask Backend

1. **Start the Flask backend first** (from the main project directory):
```bash
python app.py
```

2. **Then start the Next.js frontend** (from cyberpunk-dashboard-design):
```bash
pnpm dev
```

3. The frontend will proxy API calls to Flask via the rewrites configured in `next.config.mjs`.

### CORS Configuration (Optional)

If you encounter CORS issues when making direct API calls, you can enable CORS in Flask by installing `flask-cors`:

```bash
pip install flask-cors
```

Then add to `app.py` (after the Flask app initialization):
```python
from flask_cors import CORS
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])
```

**Note:** The Next.js rewrites configuration should handle most API calls without needing CORS.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Redirects to `/login` or `/dashboard` based on auth state |
| `/login` | Login page with device selection |
| `/register` | User registration |
| `/dashboard` | Main scoring interface with camera feed |
| `/training` | Training programs (placeholder) |
| `/analytics` | Performance analytics |
| `/history` | Past session history with shot details |
| `/profile` | User profile settings |

## Features

- 🎯 **Live Scoring** - Update scores from camera feed
- 🔫 **Mode Switching** - Toggle between Rifle and Pistol modes
- 📊 **Session Tracking** - All sessions saved to local storage
- 🎛️ **Camera Settings** - Zoom, Focus, Brightness, Contrast controls
- 📧 **Email Scoresheet** - Send results via email
- 📱 **Responsive Design** - Works on desktop and mobile

## API Endpoints Used

The frontend communicates with these Flask API endpoints:

- `GET /api/live_score` - Get scoring data
- `GET /api/rifle` / `GET /api/pistol` - Switch modes
- `GET /api/nexttarget` - Advance to next target
- `GET /api/reset` - Clear all shots
- `GET /api/focus_increase` / `GET /api/focus_decrease` - Focus control
- `GET /api/zoom_increase` / `GET /api/zoom_decrease` - Zoom control
- `POST /api/reboot` - Reboot device
- `POST /api/shutdown` - Shutdown application
- `POST /api/send_email` - Send scoresheet email

## Customization

- Colors: Edit `tailwind.config.ts` - Primary accent is `orange-500`
- Components: shadcn/ui components in `components/ui/`
- API URL: Set `NEXT_PUBLIC_API_URL` environment variable

## Tech Stack

- **Next.js 15** - React framework
- **Tailwind CSS** - Styling
- **shadcn/ui** - UI components (Radix UI based)
- **Lucide React** - Icons
- **TypeScript** - Type safety
