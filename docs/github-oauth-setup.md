# GitHub sign-in setup

Zariya uses GitHub OAuth to identify a visitor's profile. The OAuth token is exchanged and used on the server; it is not sent to browser JavaScript.

1. Create an **OAuth App** in [GitHub Developer settings](https://github.com/settings/developers).
2. Set the Homepage URL to `https://zariyas.vercel.app`.
3. Set the Authorization callback URL to `https://zariyas.vercel.app/auth/github/callback`.
4. In the Vercel project **zariya** → **Settings** → **Environment Variables**, add:
   - `GITHUB_CLIENT_ID`
   - `GITHUB_CLIENT_SECRET` (Encrypted)
5. Apply both variables to Production, Preview and Development, then redeploy the project when deployment is authorized.

The Vercel project already has a stable `FLASK_SECRET_KEY` and canonical `APP_BASE_URL` prepared. Do not commit OAuth credentials to the repository or share the Client Secret in chat.

GitHub sign-in identifies the profile only. Chats, notes and flashcards remain in browser-local storage; this feature does not create cross-device sync.
