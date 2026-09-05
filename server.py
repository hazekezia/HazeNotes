#!/usr/bin/env python3
"""
High-Performance HazeNotes Server
Powered by FastAPI, Uvicorn, SQLite (WAL mode), and WebSockets.
Optimized for 1,000+ concurrent users with sub-millisecond atomic updates.
"""

import os
import sys
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

# Ensure UTF-8 output in Windows PowerShell/cmd
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn

import database
from websocket_manager import ws_manager

# Environment Configuration
AUTH_REQUIRED = os.getenv('NOTEPAD_AUTH', 'TRUE').upper() == 'TRUE'
DEFAULT_PASSWORD = os.getenv('NOTEPAD_PASSWORD', 'admin123')
PORT = int(os.getenv('NOTEPAD_PORT', '8123'))
HOST = os.getenv('NOTEPAD_HOST', '0.0.0.0')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB & Auto-migrate legacy JSON data on start
    database.init_db()
    print(f"[Startup] SQLite initialized at {database.DB_PATH} in WAL mode.")
    yield

app = FastAPI(title="Web Notepad", lifespan=lifespan)

@app.get('/favicon.png')
async def serve_favicon():
    return FileResponse('./favicon.png', media_type='image/png')

# Helper: Authenticate Session
async def get_current_user(request: Request) -> Optional[str]:
    if not AUTH_REQUIRED:
        return 'anonymous'
    token = request.cookies.get('session')
    if not token:
        return None
    return await asyncio.to_thread(database.get_session_user, token)

# ==================== HTML TEMPLATES ====================

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign In - HazeNotes</title>
    <link rel="icon" type="image/png" href="/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #000000;
            --bg-card: rgba(18, 18, 20, 0.85);
            --border: #2a2a2a;
            --border-hover: #444444;
            --border-focus: #ffffff;
            --fg: #ffffff;
            --fg-muted: #888888;
            --fg-subtle: #555555;
            --input-bg: rgba(255, 255, 255, 0.04);
            --input-border: #262626;
            --tab-bg: #141416;
            --tab-active-bg: #222226;
            --tab-active-fg: #ffffff;
            --btn-bg: #ffffff;
            --btn-fg: #000000;
            --btn-hover: #e6e6e6;
            --accent-glow: rgba(255, 255, 255, 0.05);
            --grid-line: rgba(255, 255, 255, 0.03);
            --badge-bg: #161618;
            --badge-border: #333333;
            --toast-err-bg: rgba(239, 68, 68, 0.1);
            --toast-err-border: rgba(239, 68, 68, 0.25);
            --toast-err-fg: #fca5a5;
            --toast-suc-bg: rgba(34, 197, 94, 0.1);
            --toast-suc-border: rgba(34, 197, 94, 0.25);
            --toast-suc-fg: #86efac;
        }

        [data-theme="light"] {
            --bg-base: #fafafa;
            --bg-card: rgba(255, 255, 255, 0.92);
            --border: #e5e5e5;
            --border-hover: #cccccc;
            --border-focus: #000000;
            --fg: #111111;
            --fg-muted: #666666;
            --fg-subtle: #999999;
            --input-bg: #ffffff;
            --input-border: #e0e0e0;
            --tab-bg: #f0f0f0;
            --tab-active-bg: #ffffff;
            --tab-active-fg: #000000;
            --btn-bg: #000000;
            --btn-fg: #ffffff;
            --btn-hover: #222222;
            --accent-glow: rgba(0, 0, 0, 0.04);
            --grid-line: rgba(0, 0, 0, 0.03);
            --badge-bg: #f5f5f5;
            --badge-border: #e0e0e0;
            --toast-err-bg: #fef2f2;
            --toast-err-border: #fecaca;
            --toast-err-fg: #dc2626;
            --toast-suc-bg: #f0fdf4;
            --toast-suc-border: #bbf7d0;
            --toast-suc-fg: #16a34a;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-base);
            color: var(--fg);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 24px;
            position: relative;
            overflow-x: hidden;
            transition: background-color 0.25s ease, color 0.25s ease;
        }

        /* Subtle ambient grid background */
        body::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image: 
                linear-gradient(to right, var(--grid-line) 1px, transparent 1px),
                linear-gradient(to bottom, var(--grid-line) 1px, transparent 1px);
            background-size: 32px 32px;
            pointer-events: none;
            z-index: 0;
        }

        /* Ambient soft radial glow */
        body::after {
            content: '';
            position: absolute;
            top: 20%; left: 50%;
            transform: translate(-50%, -50%);
            width: 600px; height: 600px;
            background: radial-gradient(circle, var(--accent-glow) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
        }

        /* Top control bar */
        .top-bar {
            position: absolute;
            top: 20px;
            right: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 10;
        }

        .lang-select {
            background: var(--bg-card);
            color: var(--fg-muted);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 12px;
            padding: 6px 10px;
            cursor: pointer;
            outline: none;
            transition: all 0.2s ease;
        }
        .lang-select:hover {
            color: var(--fg);
            border-color: var(--border-hover);
        }

        .theme-toggle-btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--fg-muted);
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        .theme-toggle-btn:hover {
            color: var(--fg);
            border-color: var(--border-hover);
        }

        /* Main Card */
        .auth-card {
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 420px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 40px 36px;
            box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.4), 0 0 0 1px var(--border);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            animation: cardFadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes cardFadeIn {
            from { opacity: 0; transform: translateY(12px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        /* Branding */
        .brand-header {
            text-align: center;
            margin-bottom: 28px;
        }

        .brand-icon-box {
            width: 52px;
            height: 52px;
            margin: 0 auto 16px;
            border-radius: 12px;
            background: var(--badge-bg);
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
        }

        .brand-icon-box span {
            font-family: 'Palatino Linotype', Palatino, 'Book Antiqua', serif;
            font-size: 24px;
            font-weight: 700;
            color: var(--fg);
            letter-spacing: -0.5px;
        }

        .brand-icon-box img {
            width: 36px;
            height: 36px;
            object-fit: contain;
        }

        .brand-title {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: var(--fg);
            margin-bottom: 6px;
        }

        .brand-desc {
            font-size: 13px;
            color: var(--fg-muted);
            line-height: 1.5;
        }

        /* Tabs */
        .tab-switcher {
            display: flex;
            background: var(--tab-bg);
            padding: 4px;
            border-radius: 10px;
            border: 1px solid var(--border);
            margin-bottom: 24px;
            gap: 4px;
        }

        .tab-button {
            flex: 1;
            padding: 9px 0;
            background: transparent;
            border: none;
            border-radius: 7px;
            font-size: 13px;
            font-weight: 600;
            color: var(--fg-muted);
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .tab-button.active {
            background: var(--tab-active-bg);
            color: var(--tab-active-fg);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        }

        /* Alert Toast */
        .alert-box {
            display: none;
            align-items: center;
            gap: 10px;
            padding: 12px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 20px;
            animation: alertSlide 0.2s ease;
        }

        @keyframes alertSlide {
            from { opacity: 0; transform: translateY(-4px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .alert-box.error {
            display: flex;
            background: var(--toast-err-bg);
            border: 1px solid var(--toast-err-border);
            color: var(--toast-err-fg);
        }

        .alert-box.success {
            display: flex;
            background: var(--toast-suc-bg);
            border: 1px solid var(--toast-suc-border);
            color: var(--toast-suc-fg);
        }

        .alert-icon {
            flex-shrink: 0;
            width: 16px;
            height: 16px;
        }

        /* Form */
        .form-group {
            margin-bottom: 18px;
        }

        .form-label {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 600;
            color: var(--fg);
            margin-bottom: 7px;
            letter-spacing: -0.1px;
        }

        .label-hint {
            font-weight: 400;
            font-size: 11px;
            color: var(--fg-subtle);
        }

        .input-wrapper {
            position: relative;
            display: flex;
            align-items: center;
        }

        .input-icon {
            position: absolute;
            left: 14px;
            color: var(--fg-subtle);
            pointer-events: none;
            display: flex;
            align-items: center;
        }

        .form-input {
            width: 100%;
            padding: 11px 40px 11px 40px;
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 9px;
            color: var(--fg);
            font-family: inherit;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
        }

        .form-input:hover {
            border-color: var(--border-hover);
        }

        .form-input:focus {
            border-color: var(--border-focus);
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
        }

        [data-theme="light"] .form-input:focus {
            box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.06);
        }

        .toggle-pwd-btn {
            position: absolute;
            right: 12px;
            background: none;
            border: none;
            color: var(--fg-subtle);
            cursor: pointer;
            padding: 4px;
            display: flex;
            align-items: center;
            border-radius: 4px;
            transition: color 0.2s;
        }
        .toggle-pwd-btn:hover {
            color: var(--fg);
        }

        /* Action Button */
        .btn-submit {
            width: 100%;
            padding: 12px;
            margin-top: 8px;
            background: var(--btn-bg);
            color: var(--btn-fg);
            border: none;
            border-radius: 9px;
            font-family: inherit;
            font-size: 14px;
            font-weight: 600;
            letter-spacing: -0.2px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .btn-submit:hover {
            background: var(--btn-hover);
            transform: translateY(-1px);
        }

        .btn-submit:active {
            transform: translateY(0);
        }

        .btn-submit:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid transparent;
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            display: none;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Footer info */
        .card-footer {
            margin-top: 24px;
            padding-top: 18px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            color: var(--fg-subtle);
        }

        .badge-mono {
            font-family: 'JetBrains Mono', monospace;
            padding: 2px 6px;
            background: var(--badge-bg);
            border: 1px solid var(--badge-border);
            border-radius: 4px;
            font-size: 10px;
        }
    </style>
</head>
<body>
    <div class="top-bar">
        <select id="langSelect" class="lang-select" onchange="changeLang(this.value)">
            <option value="en">EN</option>
            <option value="id">ID</option>
        </select>
        <button id="themeToggle" class="theme-toggle-btn" type="button" title="Toggle Theme" onclick="toggleTheme()">
            <span id="themeIcon">☀️</span>
        </button>
    </div>

    <div class="auth-card">
        <div class="brand-header">
            <div class="brand-icon-box">
                <img src="/favicon.png" alt="HazeNotes">
            </div>
            <h1 class="brand-title">HazeNotes</h1>
            <p id="brandSubtitle" class="brand-desc">Minimalist, distraction-free notes with real-time collaboration</p>
        </div>

        <div class="tab-switcher">
            <button id="tabLogin" class="tab-button active" onclick="switchAuthTab('login')">Sign In</button>
            <button id="tabRegister" class="tab-button" onclick="switchAuthTab('register')">Create Account</button>
        </div>

        <div id="alertBox" class="alert-box">
            <svg class="alert-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span id="alertMsg"></span>
        </div>

        <!-- LOGIN FORM -->
        <form id="formLogin" onsubmit="submitLogin(event)">
            <div class="form-group">
                <label class="form-label" for="loginUser">
                    <span id="lblLoginUser">Username</span>
                </label>
                <div class="input-wrapper">
                    <span class="input-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                    </span>
                    <input type="text" id="loginUser" class="form-input" placeholder="e.g. haze" required autocomplete="username" autofocus>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label" for="loginPass">
                    <span id="lblLoginPass">Password</span>
                </label>
                <div class="input-wrapper">
                    <span class="input-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    </span>
                    <input type="password" id="loginPass" class="form-input" placeholder="••••••••" required autocomplete="current-password">
                    <button type="button" class="toggle-pwd-btn" onclick="togglePwd('loginPass', this)" title="Show/Hide Password">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    </button>
                </div>
            </div>

            <button type="submit" id="btnLoginSubmit" class="btn-submit">
                <div id="loginSpinner" class="spinner"></div>
                <span id="btnTextLogin">Continue</span>
            </button>
        </form>

        <!-- REGISTER FORM -->
        <form id="formRegister" style="display: none;" onsubmit="submitRegister(event)">
            <div class="form-group">
                <label class="form-label" for="regUser">
                    <span id="lblRegUser">Username</span>
                    <span id="hintRegUser" class="label-hint">Min 3 characters</span>
                </label>
                <div class="input-wrapper">
                    <span class="input-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                    </span>
                    <input type="text" id="regUser" class="form-input" placeholder="Choose a username" required minlength="3" autocomplete="username">
                </div>
            </div>

            <div class="form-group">
                <label class="form-label" for="regPass">
                    <span id="lblRegPass">Password</span>
                    <span id="hintRegPass" class="label-hint">Min 6 characters</span>
                </label>
                <div class="input-wrapper">
                    <span class="input-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    </span>
                    <input type="password" id="regPass" class="form-input" placeholder="Create strong password" required minlength="6" autocomplete="new-password">
                    <button type="button" class="toggle-pwd-btn" onclick="togglePwd('regPass', this)" title="Show/Hide Password">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    </button>
                </div>
            </div>

            <button type="submit" id="btnRegSubmit" class="btn-submit">
                <div id="regSpinner" class="spinner"></div>
                <span id="btnTextRegister">Create Account</span>
            </button>
        </form>

        <div class="card-footer">
            <span class="badge-mono">SQLite WAL • WebSockets</span>
            <span id="footerKeyHint">Press ↵ Enter</span>
        </div>
    </div>

    <script>
        // Localization
        const I18N = {
            en: {
                subtitle: 'Minimalist, distraction-free notes with real-time collaboration',
                tabLogin: 'Sign In',
                tabRegister: 'Create Account',
                user: 'Username',
                pass: 'Password',
                userHint: 'Min 3 characters',
                passHint: 'Min 6 characters',
                btnContinue: 'Continue',
                btnCreate: 'Create Account',
                btnCreating: 'Creating account…',
                btnSigning: 'Signing in…',
                footerHint: 'Press ↵ Enter',
                regSuccess: 'Account created successfully! Please sign in.',
                netErr: 'Network error. Please try again.',
                themeLight: 'Switch to light',
                themeDark: 'Switch to dark',
            },
            id: {
                subtitle: 'Catatan minimalis, bebas gangguan, dan kolaboratif secara real-time.',
                tabLogin: 'Masuk',
                tabRegister: 'Buat Akun',
                user: 'Nama Pengguna',
                pass: 'Kata Sandi',
                userHint: 'Min 3 karakter',
                passHint: 'Min 6 karakter',
                btnContinue: 'Lanjutkan',
                btnCreate: 'Buat Akun Baru',
                btnCreating: 'Membuat akun…',
                btnSigning: 'Memproses masuk…',
                footerHint: 'Tekan ↵ Enter',
                regSuccess: 'Akun berhasil dibuat! Silakan masuk.',
                netErr: 'Gagal menghubungi server. Coba lagi.',
                themeLight: 'Ganti ke terang',
                themeDark: 'Ganti ke gelap',
            }
        };

        const LANG_KEY = 'webnotepad.lang';
        const THEME_KEY = 'webnotepad.theme';

        let currentLang = localStorage.getItem(LANG_KEY) || 'en';
        if (currentLang !== 'en' && currentLang !== 'id') currentLang = 'en';

        function applyLanguage(lang) {
            currentLang = lang;
            localStorage.setItem(LANG_KEY, lang);
            document.getElementById('langSelect').value = lang;

            const t = I18N[lang] || I18N.en;
            document.getElementById('brandSubtitle').textContent = t.subtitle;
            document.getElementById('tabLogin').textContent = t.tabLogin;
            document.getElementById('tabRegister').textContent = t.tabRegister;
            document.getElementById('lblLoginUser').textContent = t.user;
            document.getElementById('lblLoginPass').textContent = t.pass;
            document.getElementById('lblRegUser').textContent = t.user;
            document.getElementById('lblRegPass').textContent = t.pass;
            document.getElementById('hintRegUser').textContent = t.userHint;
            document.getElementById('hintRegPass').textContent = t.passHint;
            document.getElementById('btnTextLogin').textContent = t.btnContinue;
            document.getElementById('btnTextRegister').textContent = t.btnCreate;
            document.getElementById('footerKeyHint').textContent = t.footerHint;
        }

        function changeLang(val) {
            applyLanguage(val);
        }

        // Theme Handling
        function getSavedTheme() {
            return localStorage.getItem(THEME_KEY) || 'auto';
        }

        function applyTheme(theme) {
            const isDark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
            if (theme === 'auto') {
                document.documentElement.removeAttribute('data-theme');
            } else {
                document.documentElement.setAttribute('data-theme', theme);
            }
            document.getElementById('themeIcon').textContent = isDark ? '☀️' : '🌙';
            document.getElementById('themeToggle').title = isDark ? (I18N[currentLang]?.themeLight || 'Light') : (I18N[currentLang]?.themeDark || 'Dark');
        }

        function toggleTheme() {
            const cur = getSavedTheme();
            let next = 'dark';
            if (cur === 'auto') {
                next = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark';
            } else if (cur === 'dark') {
                next = 'light';
            } else {
                next = 'dark';
            }
            localStorage.setItem(THEME_KEY, next);
            applyTheme(next);
        }

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
            if (getSavedTheme() === 'auto') applyTheme('auto');
        });

        // Tabs Switcher
        function switchAuthTab(mode) {
            hideAlert();
            const tabLog = document.getElementById('tabLogin');
            const tabReg = document.getElementById('tabRegister');
            const formLog = document.getElementById('formLogin');
            const formReg = document.getElementById('formRegister');

            if (mode === 'login') {
                tabLog.classList.add('active');
                tabReg.classList.remove('active');
                formLog.style.display = 'block';
                formReg.style.display = 'none';
                document.getElementById('loginUser').focus();
            } else {
                tabReg.classList.add('active');
                tabLog.classList.remove('active');
                formLog.style.display = 'none';
                formReg.style.display = 'block';
                document.getElementById('regUser').focus();
            }
        }

        function showAlert(msg, isError = true) {
            const box = document.getElementById('alertBox');
            const text = document.getElementById('alertMsg');
            box.className = 'alert-box ' + (isError ? 'error' : 'success');
            text.textContent = msg;
            box.style.display = 'flex';
        }

        function hideAlert() {
            const box = document.getElementById('alertBox');
            box.style.display = 'none';
        }

        function togglePwd(inputId, btn) {
            const input = document.getElementById(inputId);
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            btn.innerHTML = isPassword 
                ? '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/></svg>'
                : '<svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>';
        }

        // Login Handler
        async function submitLogin(e) {
            e.preventDefault();
            hideAlert();

            const username = document.getElementById('loginUser').value.trim();
            const password = document.getElementById('loginPass').value;
            const btn = document.getElementById('btnLoginSubmit');
            const spinner = document.getElementById('loginSpinner');
            const btnText = document.getElementById('btnTextLogin');
            const t = I18N[currentLang] || I18N.en;

            btn.disabled = true;
            spinner.style.display = 'inline-block';
            btnText.textContent = t.btnSigning;

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });

                const data = await res.json();
                if (res.ok) {
                    window.location.reload();
                } else {
                    showAlert(data.error || 'Authentication failed');
                }
            } catch (err) {
                showAlert(t.netErr);
            } finally {
                btn.disabled = false;
                spinner.style.display = 'none';
                btnText.textContent = t.btnContinue;
            }
        }

        // Register Handler
        async function submitRegister(e) {
            e.preventDefault();
            hideAlert();

            const username = document.getElementById('regUser').value.trim();
            const password = document.getElementById('regPass').value;
            const btn = document.getElementById('btnRegSubmit');
            const spinner = document.getElementById('regSpinner');
            const btnText = document.getElementById('btnTextRegister');
            const t = I18N[currentLang] || I18N.en;

            btn.disabled = true;
            spinner.style.display = 'inline-block';
            btnText.textContent = t.btnCreating;

            try {
                const res = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });

                const data = await res.json();
                if (res.ok) {
                    switchAuthTab('login');
                    showAlert(t.regSuccess, false);
                    document.getElementById('loginUser').value = username;
                    document.getElementById('loginPass').focus();
                } else {
                    showAlert(data.error || 'Registration failed');
                }
            } catch (err) {
                showAlert(t.netErr);
            } finally {
                btn.disabled = false;
                spinner.style.display = 'none';
                btnText.textContent = t.btnCreate;
            }
        }

        // Initial setup
        applyTheme(getSavedTheme());
        applyLanguage(currentLang);
    </script>
</body>
</html>'''

NOTEPAD_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HazeNotes</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>
  :root{--bg:#000000;--fg:#ffffff;--muted:#cccccc;--bar-border:#333333;--tab-bg:#1a1a1a;--tab-border:#333333;--tab-fg:#eeeeee;--tab-active-bg:#222222;--tab-active-border:#ffffff;--tab-active-fg:#ffffff;--tab-x:#666666;--tab-x-hover-bg:#333333;--tab-add:#888888;--tab-add-hover:#ffffff;--tab-focus-bg:#111111;--tab-focus-ring:#ffffff;--ph:#444444;--scrollbar:#333333;--icon:#aaaaaa;--icon-hover:#ffffff;--icon-bg-hover:#222222;--nav:#cccccc;--nav-hover:#ffffff;--nav-hover-bg:#333333;--fade:rgba(0,0,0,0)}
  [data-theme=light]{--bg:#ffffff;--fg:#000000;--muted:#444444;--bar-border:#dddddd;--tab-bg:#eeeeee;--tab-border:#bbbbbb;--tab-fg:#111111;--tab-active-bg:#f5f5f5;--tab-active-border:#000000;--tab-active-fg:#000000;--tab-x:#666666;--tab-x-hover-bg:#dddddd;--tab-add:#888888;--tab-add-hover:#000000;--tab-focus-bg:#fafafa;--tab-focus-ring:#000000;--ph:#888888;--scrollbar:#bbbbbb;--icon:#555555;--icon-hover:#000000;--icon-bg-hover:#ddd}
  @media (prefers-color-scheme:light){:root:not([data-theme]){--bg:#ffffff;--fg:#000000;--muted:#444444;--bar-border:#dddddd;--tab-bg:#eeeeee;--tab-border:#bbbbbb;--tab-fg:#111111;--tab-active-bg:#f5f5f5;--tab-active-border:#000000;--tab-active-fg:#000000;--tab-x:#666666;--tab-x-hover-bg:#dddddd;--tab-add:#888888;--tab-add-hover:#000000;--tab-focus-bg:#fafafa;--tab-focus-ring:#000000;--ph:#888888;--scrollbar:#bbbbbb;--icon:#555555;--icon-hover:#000000;--icon-bg-hover:#dddddd;--nav:#444444;--nav-hover:#000000;--nav-hover-bg:#dddddd;--fade:rgba(255,255,255,0)}}
  body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);display:flex;flex-direction:column;height:100vh}
  #bar{padding:8px 16px;font-size:13px;color:var(--muted);display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--bar-border);flex:0 0 auto;gap:8px;position:relative}
  #bar>span:first-child{flex:0 0 auto}
  .tabnav{background:transparent;border:1px solid transparent;color:var(--nav);width:24px;height:24px;border-radius:6px;cursor:pointer;display:none;align-items:center;justify-content:center;font-size:14px;padding:0;flex:0 0 auto;line-height:1}
  .tabnav.show{display:inline-flex}
  .tabnav:hover{color:var(--nav-hover);background:var(--nav-hover-bg)}
  #tabs-wrap{position:relative;flex:1 1 auto;min-width:0;display:flex;align-items:center;margin:0 4px}
  #tabs{display:flex;gap:2px;flex:1 1 auto;min-width:0;overflow-x:auto;overflow-y:hidden;align-items:center;scrollbar-width:none;-ms-overflow-style:none;scroll-behavior:smooth}
  #tabs::-webkit-scrollbar{display:none}
  #tabs-wrap .fade-l,#tabs-wrap .fade-r{position:absolute;top:0;bottom:0;width:24px;pointer-events:none;opacity:0;transition:opacity .15s}
  #tabs-wrap .fade-l{left:0;background:linear-gradient(to right,var(--bg),var(--fade))}
  #tabs-wrap .fade-r{right:0;background:linear-gradient(to left,var(--bg),var(--fade))}
  #tabs-wrap .fade-l.show,#tabs-wrap .fade-r.show{opacity:1}
  .tab{display:inline-flex;align-items:center;gap:6px;padding:4px 10px 4px 12px;background:var(--tab-bg);border:1px solid var(--tab-border);border-radius:6px;font-size:12px;color:var(--tab-fg);cursor:pointer;max-width:180px;flex:0 0 auto;user-select:none}
  .tab.active{background:var(--tab-active-bg);border-color:var(--tab-active-border);color:var(--tab-active-fg)}
  .tab .tt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px;outline:none;cursor:text;border-radius:3px;padding:0 2px}
  .tab .tt:focus{background:var(--tab-focus-bg);box-shadow:0 0 0 1px var(--tab-focus-ring)}
  .tab .x{color:var(--tab-x);font-size:14px;line-height:1;padding:0 2px;border-radius:3px}
  .tab .x:hover{color:var(--icon-hover);background:var(--tab-x-hover-bg)}
  .tab .sh{color:var(--tab-x);font-size:12px;line-height:1;padding:0 2px;border-radius:3px}
  .tab .sh:hover{color:var(--icon-hover);background:var(--tab-x-hover-bg)}
  .collaborator-actions select{background:var(--tab-bg);color:var(--fg);border:1px solid var(--tab-border);border-radius:4px;padding:3px 6px;margin-right:6px;cursor:pointer}
  .collaborator-actions select option{background:var(--bg);color:var(--fg)}
  .tab.add{background:transparent;border-style:dashed;color:var(--tab-add)}
  .tab.add:hover{color:var(--tab-add-hover);border-color:var(--icon-hover)}
  #t{width:100%;flex:1 1 auto;box-sizing:border-box;outline:0;cursor:text;background:var(--bg);color:var(--fg);font:15px/1.7 ui-monospace,monospace;padding:20px 24px;overflow-y:auto;margin:0}
  #t:empty::before{content:attr(data-ph);color:var(--ph)}
  #t img{max-width:100%;height:auto;border-radius:6px;margin:8px 0;display:block}
  #t img:active,#t img:focus{outline:2px solid var(--tab-focus-ring)}
  #themeBtn,#featureBtn{background:transparent;border:1px solid transparent;color:var(--icon);width:28px;height:28px;border-radius:6px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:14px;padding:0;flex:0 0 auto}
  #themeBtn:hover,#featureBtn:hover{color:var(--icon-hover);background:var(--icon-bg-hover)}
  #langSel{background:transparent;color:var(--icon);border:1px solid var(--tab-border);border-radius:6px;font:inherit;font-size:12px;padding:3px 6px;cursor:pointer;height:28px;flex:0 0 auto}
  #langSel:hover{color:var(--icon-hover);background:var(--icon-bg-hover)}
  #langSel option{background:var(--bg);color:var(--fg)}
  #userInfo{color:var(--fg);font-size:12px;padding:4px 10px;background:var(--tab-bg);border-radius:6px}
  #logoutBtn{background:transparent;border:1px solid transparent;color:var(--icon);width:28px;height:28px;border-radius:6px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:14px;padding:0;flex:0 0 auto}
  #logoutBtn:hover{color:var(--icon-hover);background:var(--icon-bg-hover)}
  
  /* Collaboration modal */
  .modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000;align-items:center;justify-content:center}
  .modal.show{display:flex}
  .modal-content{background:var(--bg);padding:30px;border-radius:12px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto}
  .modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
  .modal-title{font-size:20px;font-weight:600;color:var(--fg)}
  .close-btn{background:none;border:none;color:var(--fg);font-size:24px;cursor:pointer}
  .share-section{margin-top:20px}
  .collaborator-list{list-style:none;padding:0;margin:15px 0}
  .collaborator-item{display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--tab-bg);border-radius:6px;margin-bottom:8px}
  .collaborator-actions button{background:var(--tab-active-bg);color:var(--fg);border:none;padding:4px 10px;border-radius:4px;cursor:pointer}
  .share-link-input{width:100%;padding:10px;margin:10px 0;background:var(--tab-bg);border:1px solid var(--tab-border);color:var(--fg);border-radius:6px;box-sizing:border-box}
  .info-button{color:var(--nav);font-size:18px}
  
  @media (prefers-color-scheme:light){:root:not([data-theme]){--nav:#999;--nav-hover:#1a1a1a;--nav-hover-bg:#e0e0e0}}
</style>
<div id="bar">
  <span>HazeNotes <span id="userInfo" style="display:USER_INFO_STYLE_PLACEHOLDER_">{CURRENT_USER_DISPLAY}</span></span>
  <div id="tabs-wrap">
    <button id="tabPrev" class="tabnav" type="button" title="Scroll left">‹</button>
    <div id="tabs"></div>
    <button id="tabNext" class="tabnav" type="button" title="Scroll right">›</button>
    <div class="fade-l"></div>
    <div class="fade-r"></div>
  </div>
  <span id="st"></span>
  <select id="langSel" title="Language">
    <option value="en">EN</option>
    <option value="id">ID</option>
  </select>
  <button id="featureBtn" type="button" title="Features">&nbsp;✦&nbsp;</button>
  <button id="themeBtn" type="button" title="Toggle dark/light"></button>
  [LOGOUT_BUTTON_PLACEHOLDER]
</div>
<div id="t" data-ph="Type here... paste images with Ctrl+V" contenteditable="true"></div>

<!-- Collaboration Modal -->
<div id="shareModal" class="modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2 class="modal-title">Share Note</h2>
      <button class="close-btn" onclick="closeShareModal()">×</button>
    </div>
    <div class="share-section">
      <p style="color:var(--muted);font-size:13px;">Add collaborators to share this note:</p>
      <input type="text" id="collaboratorInput" class="share-link-input" placeholder="Enter username to share with">
      <select id="collaboratorRole" class="share-link-input" style="cursor:pointer;">
        <option value="edit">Can edit</option>
        <option value="read">Read only</option>
      </select>
      <button onclick="addCollaborator()" style="width:100%;padding:10px;background:var(--tab-active-bg);color:var(--fg);border:none;border-radius:6px;cursor:pointer;">Add Collaborator</button>
      
      <ul id="collaboratorList" class="collaborator-list"></ul>
      
      <hr style="border:1px solid var(--bar-border);margin:20px 0;">
      
      <p style="color:var(--muted);font-size:13px;">Your note link:</p>
      <input type="text" id="shareLink" class="share-link-input" readonly>
      <button onclick="copyLink()" style="width:100%;padding:10px;background:var(--tab-active-bg);color:var(--fg);border:none;border-radius:6px;cursor:pointer;">Copy Link</button>
    </div>
  </div>
</div>

<!-- Features Info Modal -->
<div id="featuresModal" class="modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2 class="modal-title">✨ Features</h2>
      <button class="close-btn" onclick="closeFeaturesModal()">×</button>
    </div>
    <div style="line-height:1.8;">
      <h3 style="margin-top:20px;">🔐 Authentication</h3>
      <p>If authentication is enabled, you need to login to access your personal notes.</p>
      
      <h3 style="margin-top:20px;">📝 User-Specific Notes</h3>
      <p>Each user has their own separate notes. Your notes are private by default.</p>
      
      <h3 style="margin-top:20px;">🤝 Collaboration</h3>
      <p>Share your notes with other users. They can view and edit the same note in real-time!</p>
      
      <h3 style="margin-top:20px;">⚡ High Performance Real-Time Sync</h3>
      <p>Instant synchronization via persistent WebSockets & SQLite WAL mode for fast concurrency.</p>
      
      <h3 style="margin-top:20px;">🖼️ Image Support</h3>
      <p>Paste or drag & drop images directly into your notes.</p>
      
      <h3 style="margin-top:20px;">🌗 Dark/Light Mode</h3>
      <p>Switch between dark and light themes based on your preference.</p>
      
      <h3 style="margin-top:20px;">📱 Multi-Language</h3>
      <p>Support for English and Indonesian languages.</p>
    </div>
  </div>
</div>

<script>
const t=document.getElementById('t'),tabsEl=document.getElementById('tabs'),st=document.getElementById('st');
const I18N={
  en:{
    untitled:'Untitled',newTab:'New tab',renameHint:'Click to edit',
    addTab:'New note',defaultTitle:'New Note',firstNote:'New Note',
    deleteConfirm:'Delete this note?',leaveConfirm:'Leave this shared note?',
    titlePrompt:'Note title:',
    saved:'Saved',saving:'Saving…',saveFail:'Save failed',
    placeholder:'Type here... paste images with Ctrl+V',
    themeDark:'Switch to dark',themeLight:'Switch to light',
    imageAlt:'image',noTitle:'Untitled',
    shareTitle:'Share Note',addCollaborator:'Add Collaborator',
    copyLink:'Copy Link',linkCopied:'Link copied!',remove:'Remove',
    roleEdit:'Can edit',readOnly:'Read only',
    enterUsername:'Enter username',yourLink:'Your note link',
    collabNote:'Shared note',ownedBy:'Owned by',
  },
  id:{
    untitled:'Tanpa judul',newTab:'Tab baru',renameHint:'Klik untuk edit',
    addTab:'Tambah note baru',defaultTitle:'New Note',firstNote:'New Note',
    deleteConfirm:'Hapus note ini?',leaveConfirm:'Keluar dari note bersama ini?',
    titlePrompt:'Judul note:',
    saved:'Tersimpan',saving:'Menyimpan…',saveFail:'Gagal simpan',
    placeholder:'Tulis di sini... tempel gambar dengan Ctrl+V',
    themeDark:'Ganti ke gelap',themeLight:'Ganti ke terang',
    imageAlt:'gambar',noTitle:'Tanpa judul',
    shareTitle:'Bagikan Note',addCollaborator:'Tambah Kolaborator',
    copyLink:'Salin Link',linkCopied:'Link disalin!',remove:'Hapus',
    roleEdit:'Bisa edit',readOnly:'Baca saja',
    enterUsername:'Masukkan nama pengguna',yourLink:'Link note Anda',
    collabNote:'Note bersama',ownedBy:'Milik',
  },
};
const LANG_KEY='webnotepad.lang';
let lang=localStorage.getItem(LANG_KEY);
if(lang!=='en'&&lang!=='id') lang='en';
const t9n=(k)=>(I18N[lang]&&I18N[lang][k])||I18N.en[k]||k;

let timer,lastSent=null,currentId=null,notes=[],dirty=false,saving=false,currentUser=CURRENT_USER_PLACEHOLDER_;
let noteRoles={},canEditCurrent=true;
const featuresEnabled=true;

// ==================== REAL-TIME WEBSOCKET CLIENT ====================
let ws = null;
let wsReconnectTimer = null;

function connectWS(noteId){
  if(ws){
    try { ws.close(); } catch(e){}
    ws = null;
  }
  if(!noteId) return;
  clearTimeout(wsReconnectTimer);
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/notes/${noteId}`;
  
  try {
    ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
      if(saving || dirty) return; // Do not overwrite uncommitted local edits
      try {
        const msg = JSON.parse(event.data);
        if(msg.type === 'note_update' && msg.note_id === currentId){
          const remote = msg.note != null ? msg.note : '';
          if(remote !== lastSent){
            lastSent = remote;
            const cur = looksHTML(remote) ? t.innerHTML : t.textContent;
            if(cur !== remote){
              const off = document.activeElement === t ? caretOffset() : null;
              if(looksHTML(remote)) renderSafe(remote); else t.textContent = remote;
              if(off != null) setCaret(off); else caretEnd();
              st.textContent = t9n('saved');
            }
          }
          if(msg.title){
            const n = notes.find(x => x.id === currentId);
            if(n && n.title !== msg.title){
              n.title = msg.title;
              renderTabs();
            }
          }
        } else if(msg.type === 'note_deleted' && msg.note_id === currentId){
          loadNotes();
        }
      } catch(e){}
    };
    
    ws.onclose = () => {
      // Reconnect automatically if still on the same note
      if(currentId === noteId){
        wsReconnectTimer = setTimeout(() => {
          if(currentId === noteId) connectWS(noteId);
        }, 2000);
      }
    };
  } catch(e){}
}

const looksHTML=s=>/<(img|div|p|br|h[1-6]|ul|ol|li|table|pre|blockquote|hr)\b/i.test(s||'');

function renderSafe(html){
  const dp=new DOMParser().parseFromString('<div>'+html+'</div>','text/html');
  const root=dp.body.firstChild;
  const bad=root.querySelectorAll('script,iframe,object,embed,style,link,meta');
  bad.forEach(n=>n.remove());
  const walker=dp.createTreeWalker(root,NodeFilter.SHOW_ELEMENT);
  let el=walker.nextNode();
  while(el){
    for(const a of [...el.attributes]){
      if(/^on/i.test(a.name)||/^javascript:/i.test(a.value)) el.removeAttribute(a.name);
    }
    if(el.tagName==='A'&&el.href&&!/^https?:\/\//i.test(el.href)&&!/^mailto:/i.test(el.href)) el.removeAttribute('href');
    el=walker.nextNode();
  }
  root.querySelectorAll('img[src]').forEach(img=>{
    if(!/^\/images\//.test(img.getAttribute('src'))) img.removeAttribute('src');
  });
  const frag=document.createDocumentFragment();
  while(root.firstChild) frag.appendChild(root.firstChild);
  t.replaceChildren(frag);
}

function updateNav(){
  const canLeft=tabsEl.scrollLeft>1;
  const canRight=tabsEl.scrollLeft<tabsEl.scrollWidth-tabsEl.clientWidth-1;
  document.getElementById('tabPrev').classList.toggle('show',canLeft);
  document.getElementById('tabNext').classList.toggle('show',canRight);
  document.querySelector('.fade-l').classList.toggle('show',canLeft);
  document.querySelector('.fade-r').classList.toggle('show',canRight);
}
document.getElementById('tabPrev').onclick=()=>tabsEl.scrollBy({left:-150,behavior:'smooth'});
document.getElementById('tabNext').onclick=()=>tabsEl.scrollBy({left:150,behavior:'smooth'});
tabsEl.addEventListener('scroll',updateNav,{passive:true});

function renderTabs(){
  tabsEl.innerHTML='';
  for(const n of notes){
    const tab=document.createElement('div');
    tab.className='tab'+(n.id===currentId?' active':'');
    tab.dataset.id=n.id;
    
    // Collab indicator icon
    const isOwner=n.is_owner!==false;
    const isCollab=n.is_collab===true;
    if(isCollab){
      const ci=document.createElement('span');
      ci.className='sh';
      ci.textContent='👥';
      ci.title=isOwner?t9n('collabNote'):(t9n('ownedBy')+' '+n.owner);
      ci.style.cursor='default';
      tab.appendChild(ci);
    }
    
    const tt=document.createElement('span');
    tt.className='tt';
    tt.textContent=n.title||t9n('untitled');
    tt.title=t9n('renameHint');
    tab.appendChild(tt);
    
    // Share button (only for owner)
    if(isOwner){
      const sh=document.createElement('span');
      sh.className='sh';
      sh.innerHTML='🔗';
      sh.title=t9n('shareTitle');
      sh.onclick=(e)=>{e.stopPropagation();openShareModal(n.id);};
      tab.appendChild(sh);
    }
    
    if(notes.length>1){
      const x=document.createElement('span');
      x.className='x';
      x.textContent='×';
      x.title=isOwner?t9n('deleteConfirm'):t9n('leaveConfirm');
      x.onclick=(e)=>{e.stopPropagation();deleteNote(n.id);};
      tab.appendChild(x);
    }
    tab.onclick=()=>{if(n.id!==currentId) switchNote(n.id);};
    tabsEl.appendChild(tab);
  }
  const add=document.createElement('div');
  add.className='tab add';
  add.textContent='+';
  add.title=t9n('addTab');
  add.onclick=createNote;
  tabsEl.appendChild(add);
  enableRename();
  updateNav();
}

async function loadNotes(){
  const d=await (await fetch('/api/notes')).json();
  notes=(d.notes||[]).map(n=>({
    id:n.id, title:n.title, owner:n.owner,
    is_owner:n.is_owner, is_collab:n.is_collab,
    collab_count:n.collab_count, user_role:n.user_role
  }));
  if(!notes.length){
    const r=await (await fetch('/api/notes',{method:'POST',body:JSON.stringify({title:t9n('firstNote')}),headers:{'Content-Type':'application/json'}})).json();
    notes=[{id:r.id,title:r.title,is_owner:true,is_collab:false,owner:currentUser}];
  }
  await switchNote(notes[0].id, false);
  renderTabs();
}

async function switchNote(id, refreshTabs=true){
  if(currentId && currentId!==id && t.innerHTML!==''){
    clearTimeout(timer); dirty=false;
    const prev=notes.find(x=>x.id===currentId)||{};
    fetch('/api/notes/'+currentId,{method:'POST',
      body:JSON.stringify({title:prev.title||'',note:t.innerHTML}),
      headers:{'Content-Type':'application/json'}}).catch(()=>{});
  }
  currentId=id;
  const d=await (await fetch('/api/notes/'+id)).json();
  noteRoles[id]={owner:d.created_by,roles:d.collaborators||{}};
  canEditCurrent=d.created_by===currentUser||(d.collaborators||{})[currentUser]==='edit';
  t.contentEditable=canEditCurrent?'true':'false';
  lastSent=d.note||'';
  if(looksHTML(lastSent)) renderSafe(lastSent); else t.textContent=lastSent;
  st.textContent=canEditCurrent?t9n('saved'):t9n('readOnly');
  
  // Connect real-time WebSocket for the active note
  connectWS(id);
  
  if(refreshTabs) renderTabs();
}

async function createNote(){
  const r=await (await fetch('/api/notes',{method:'POST',body:JSON.stringify({title:t9n('defaultTitle')}),headers:{'Content-Type':'application/json'}})).json();
  notes.push({id:r.id,title:r.title});
  await switchNote(r.id);
  renderTabs();
}

async function deleteNote(id){
  const n=notes.find(x=>x.id===id);
  const isOwner=!n||n.is_owner!==false;
  const msg=isOwner?t9n('deleteConfirm'):t9n('leaveConfirm');
  if(!confirm(msg)) return;
  const res=await fetch('/api/notes/'+id,{method:'DELETE'});
  if(!res.ok){
    const err=await res.json().catch(()=>({}));
    alert(err.error||'Failed'); return;
  }
  notes=notes.filter(x=>x.id!==id);
  delete noteRoles[id];
  if(currentId===id){
    if(!notes.length){await createNote();return;}
    await switchNote(notes[0].id);
  }else{
    renderTabs();
  }
}

async function renameTab(id){
  const n=notes.find(x=>x.id===id);if(!n) return;
  const meta=noteRoles[id];
  if(meta && meta.owner!==currentUser && meta.roles[currentUser]!=='edit') return;
  if(currentId!==id) await switchNote(id);
  const tt=tabsEl.querySelector(`.tab[data-id="${id}"] .tt`);if(!tt) return;
  const finish=(commit)=>{
    tt.contentEditable='false';
    const val=tt.textContent.trim()||t9n('untitled');
    tt.textContent=val;
    if(commit&&val!==n.title){
      n.title=val;
      fetch('/api/notes/'+id,{method:'POST',body:JSON.stringify({title:val,note:t.innerHTML}),headers:{'Content-Type':'application/json'}});
    }
  };
  tt.contentEditable='true';
  tt.focus();
  const r=document.createRange(); r.selectNodeContents(tt);
  const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
  tt.onkeydown=(e)=>{
    if(e.key==='Enter'){e.preventDefault();finish(true);}
    else if(e.key==='Escape'){e.preventDefault();finish(false);}
  };
  tt.onblur=()=>finish(true);
}

function enableRename(){
  tabsEl.querySelectorAll('.tab').forEach(tab=>{
    const id=tab.dataset.id;
    if(!id) return;
    const tt=tab.querySelector('.tt');
    if(!tt) return;
    tt.onclick=(e)=>{e.stopPropagation();renameTab(id);};
  });
}

function save(){
  st.textContent=t9n('saving');
  if(!currentId) return;
  if(!canEditCurrent) return;
  saving=true;
  const id=currentId;
  const title=(notes.find(n=>n.id===id)||{}).title||'';
  const body=t.innerHTML;
  fetch('/api/notes/'+id,{method:'POST',body:JSON.stringify({title,note:body}),headers:{'Content-Type':'application/json'}})
    .then(()=>{lastSent=body; saving=false; if(!dirty) st.textContent=t9n('saved');})
    .catch(()=>{saving=false; st.textContent=t9n('saveFail');});
}
t.addEventListener('input',()=>{st.textContent=t9n('saving');dirty=true;clearTimeout(timer);timer=setTimeout(()=>{dirty=false;save();},500)});

function uploadImages(files){
  let done=0;
  files.forEach(f=>{
    fetch('/api/upload',{method:'POST',body:f}).then(r=>r.json()).then(d=>{
      if(d.url) document.execCommand('insertHTML',false,'<img src="'+d.url+'" alt="gambar">');
    }).finally(()=>{if(++done===files.length) save()});
  });
}
t.addEventListener('paste',e=>{
  const files=[...(e.clipboardData?.files||[])].filter(f=>f.type.startsWith('image/'));
  if(!files.length) return;
  e.preventDefault();
  uploadImages(files);
});
t.addEventListener('dragover',e=>e.preventDefault());
t.addEventListener('drop',e=>{
  e.preventDefault();
  const files=[...(e.dataTransfer.files||[])].filter(f=>f.type.startsWith('image/'));
  if(files.length) uploadImages(files);
});

function caretOffset(){
  const sel=window.getSelection();
  if(!sel.rangeCount) return null;
  const range=sel.getRangeAt(0);
  const pre=range.cloneRange();
  pre.selectNodeContents(t);
  pre.setEnd(range.startContainer,range.startOffset);
  return pre.toString().length;
}
function setCaret(off){
  if(off==null) return;
  const w=document.createTreeWalker(t,NodeFilter.SHOW_TEXT);
  let node,acc=0;
  while((node=w.nextNode())){
    const l=node.data.length;
    if(acc+l>=off){
      const r=document.createRange();
      r.setStart(node,Math.min(off-acc,l)); r.collapse(true);
      const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
      return;
    }
    acc+=l;
  }
}
function caretEnd(){
  const r=document.createRange(); r.selectNodeContents(t); r.collapse(false);
  const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
}

function applyLang(){
  t.setAttribute('data-ph', t9n('placeholder'));
  st.textContent=(saving||dirty) ? t9n('saving') : (!canEditCurrent ? t9n('readOnly') : t9n('saved'));
  renderTabs();
}
document.getElementById('langSel').value=lang;
document.getElementById('langSel').onchange=(e)=>{
  lang=e.target.value;
  localStorage.setItem(LANG_KEY,lang);
  applyLang();
};

const THEME_KEY='webnotepad.theme';
function getTheme(){return localStorage.getItem(THEME_KEY)||'auto'}
function applyTheme(theme){
  if(theme==='auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',theme);
  const isDark=theme==='dark'||(theme==='auto'&&window.matchMedia('(prefers-color-scheme:dark)').matches);
  document.getElementById('themeBtn').textContent=isDark?'☀':'🌙';
  document.getElementById('themeBtn').title=isDark?t9n('themeLight'):t9n('themeDark');
}
document.getElementById('themeBtn').onclick=()=>{
  const cur=getTheme();
  let next='auto';
  if(cur==='auto') next=window.matchMedia('(prefers-color-scheme:dark)').matches?'light':'dark';
  else if(cur==='dark') next='light';
  else next='dark';
  localStorage.setItem(THEME_KEY,next);
  applyTheme(next);
};
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{
  if(getTheme()==='auto') applyTheme('auto');
});

// Features modal
document.getElementById('featureBtn').onclick=()=>document.getElementById('featuresModal').classList.add('show');
function closeFeaturesModal(){document.getElementById('featuresModal').classList.remove('show');}

// Share modal
async function openShareModal(noteId){
  const modal=document.getElementById('shareModal');
  modal.classList.add('show');
  modal.dataset.noteId=noteId;
  document.getElementById('shareLink').value=window.location.origin+'?note='+noteId;
  await loadCollaborators(noteId);
}
function closeShareModal(){document.getElementById('shareModal').classList.remove('show');}

async function loadCollaborators(noteId){
  const d=await (await fetch('/api/notes/'+noteId)).json();
  const list=document.getElementById('collaboratorList');
  list.innerHTML='';
  const collabs=d.collaborators||{};
  for(const [username,role] of Object.entries(collabs)){
    const li=document.createElement('li');
    li.className='collaborator-item';
    li.innerHTML=`<span>${username}</span><div class="collaborator-actions"><select onchange="updateRole('${noteId}','${username}',this.value)"><option value="edit" ${role==='edit'?'selected':''}>${t9n('roleEdit')}</option><option value="read" ${role==='read'?'selected':''}>${t9n('readOnly')}</option></select><button onclick="removeCollaborator('${noteId}','${username}')">${t9n('remove')}</button></div>`;
    list.appendChild(li);
  }
}

async function addCollaborator(){
  const noteId=document.getElementById('shareModal').dataset.noteId;
  const username=document.getElementById('collaboratorInput').value.trim();
  const role=document.getElementById('collaboratorRole').value;
  if(!username) return;
  const res=await fetch(`/api/notes/${noteId}/share`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username,role})
  });
  if(res.ok){
    document.getElementById('collaboratorInput').value='';
    await loadCollaborators(noteId);
  }else{
    const d=await res.json();
    alert(d.error||'Failed to add collaborator');
  }
}

async function removeCollaborator(noteId,username){
  await fetch(`/api/notes/${noteId}/share`,{
    method:'DELETE',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username})
  });
  await loadCollaborators(noteId);
}

async function updateRole(noteId,username,role){
  await fetch(`/api/notes/${noteId}/share`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username,role})
  });
}

function copyLink(){
  const input=document.getElementById('shareLink');
  input.select();
  navigator.clipboard.writeText(input.value);
  alert(t9n('linkCopied'));
}

window.onclick=(e)=>{
  if(e.target.classList.contains('modal')) e.target.classList.remove('show');
};

LOGOUT_SCRIPT_PLACEHOLDER

applyTheme(getTheme());
applyLang();
loadNotes();
</script>
</html>'''

def render_notepad_page(current_user: Optional[str]) -> str:
    user_display = current_user if current_user and current_user != 'anonymous' else ''
    user_info_style = 'inline' if user_display else 'none'
    logout_btn = '<button id="logoutBtn" type="button" title="Logout">🚪</button>' if user_display else ''
    logout_script = ''
    if user_display:
        logout_script = 'document.getElementById("logoutBtn").onclick = () => { fetch("/api/auth/logout", {method: "POST"}).then(() => window.location.reload()); };'
        
    html = NOTEPAD_HTML_TEMPLATE.replace('USER_INFO_STYLE_PLACEHOLDER_', user_info_style)
    html = html.replace('{CURRENT_USER_DISPLAY}', user_display)
    html = html.replace('[LOGOUT_BUTTON_PLACEHOLDER]', logout_btn)
    html = html.replace('CURRENT_USER_PLACEHOLDER_', json.dumps(current_user or 'anonymous'))
    html = html.replace('LOGOUT_SCRIPT_PLACEHOLDER', logout_script)
    return html

# ==================== ROUTE HANDLERS ====================

@app.get('/', response_class=HTMLResponse)
@app.get('/index.html', response_class=HTMLResponse)
async def serve_index(request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return HTMLResponse(LOGIN_HTML)
    return HTMLResponse(render_notepad_page(user))

# Authentication Endpoints
@app.post('/api/auth/login')
async def handle_login(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)
        
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user = await asyncio.to_thread(database.get_user, username)
    if not user or user['password'] != database.hash_password(password):
        return JSONResponse({'error': 'Invalid username or password'}, status_code=401)
        
    token = await asyncio.to_thread(database.create_session, username)
    response = JSONResponse({'status': 'ok', 'username': username})
    response.set_cookie('session', token, httponly=True, samesite='lax', path='/')
    return response

@app.get('/api/auth/login')
async def handle_anonymous_login():
    if AUTH_REQUIRED:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    return JSONResponse({'status': 'ok', 'username': 'anonymous'})

@app.post('/api/auth/register')
async def handle_register(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid request body'}, status_code=400)
        
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or len(username) < 3:
        return JSONResponse({'error': 'Username must be at least 3 characters'}, status_code=400)
    if not password or len(password) < 6:
        return JSONResponse({'error': 'Password must be at least 6 characters'}, status_code=400)
        
    pwd_hash = database.hash_password(password)
    success = await asyncio.to_thread(database.create_user, username, pwd_hash)
    if not success:
        return JSONResponse({'error': 'Username already exists'}, status_code=400)
        
    return JSONResponse({'status': 'ok', 'message': 'Account created successfully'})

@app.post('/api/auth/logout')
async def handle_logout(request: Request):
    token = request.cookies.get('session')
    if token:
        await asyncio.to_thread(database.delete_session, token)
    response = JSONResponse({'status': 'ok'})
    response.delete_cookie('session', path='/')
    return response

# Notes Endpoints
@app.get('/api/notes')
async def list_notes(request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    notes = await asyncio.to_thread(database.get_user_notes, user or 'anonymous')
    return {'notes': notes}

@app.post('/api/notes')
async def create_note(request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    try:
        data = await request.json()
    except Exception:
        data = {}
    title = data.get('title', 'New Note')
    note_id = uuid.uuid4().hex[:16]
    note = await asyncio.to_thread(database.create_note, note_id, title, user or 'anonymous', '')
    return {'id': note['id'], 'title': note['title']}

@app.get('/api/notes/{note_id}')
async def get_note_detail(note_id: str, request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    note = await asyncio.to_thread(database.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
        
    # Permission verification
    if AUTH_REQUIRED and user != note['owner'] and user not in note['collaborators']:
        return JSONResponse({'error': 'Access denied'}, status_code=403)
        
    return {
        'id': note['id'],
        'title': note['title'],
        'note': note['content'],
        'created_by': note['owner'],
        'created_at': note['created_at'],
        'updated_at': note['updated_at'],
        'collaborators': note['collaborators']
    }

@app.post('/api/notes/{note_id}')
@app.put('/api/notes/{note_id}')
async def update_note(note_id: str, request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    note = await asyncio.to_thread(database.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
        
    # Permission check: owner or collaborator with edit role
    if AUTH_REQUIRED:
        if user != note['owner'] and note['collaborators'].get(user) != 'edit':
            return JSONResponse({'error': 'Permission denied'}, status_code=403)
            
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)
        
    title = data.get('title')
    content = data.get('note')
    
    await asyncio.to_thread(database.update_note, note_id, title, content)
    
    # Broadcast to other WebSocket subscribers in real-time
    ws_payload = {'type': 'note_update', 'note_id': note_id, 'sender': user}
    if content is not None:
        ws_payload['note'] = content
    if title is not None:
        ws_payload['title'] = title
    await ws_manager.broadcast(note_id, ws_payload)
    
    return {'status': 'ok'}

@app.delete('/api/notes/{note_id}')
async def delete_note(note_id: str, request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    note = await asyncio.to_thread(database.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
    
    if AUTH_REQUIRED and user != note['owner']:
        # Collaborator: leave the note (remove self from collaborators)
        if user in note.get('collaborators', {}):
            await asyncio.to_thread(database.remove_collaborator, note_id, user)
            return {'left': True, 'note_id': note_id}
        return JSONResponse({'error': 'Access denied'}, status_code=403)
    
    # Owner: fully delete the note
    await asyncio.to_thread(database.delete_note, note_id)
    await ws_manager.broadcast(note_id, {'type': 'note_deleted', 'note_id': note_id})
    return {'deleted': True}

@app.post('/api/notes/{note_id}/share')
async def add_collaborator(note_id: str, request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    note = await asyncio.to_thread(database.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
    if AUTH_REQUIRED and user != note['owner']:
        return JSONResponse({'error': 'Only owner can share'}, status_code=403)
        
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)
        
    target_user = data.get('username', '').strip()
    role = data.get('role', 'edit')
    
    if not target_user:
        return JSONResponse({'error': 'Username required'}, status_code=400)
    if target_user == note['owner']:
        return JSONResponse({'error': 'Cannot add owner as collaborator'}, status_code=400)
        
    success = await asyncio.to_thread(database.add_collaborator, note_id, target_user, role)
    if not success:
        return JSONResponse({'error': f'User "{target_user}" not found'}, status_code=404)
        
    updated = await asyncio.to_thread(database.get_note, note_id)
    return {'note': {'id': updated['id'], 'title': updated['title'], 'collaborators': updated['collaborators']}}

@app.delete('/api/notes/{note_id}/share')
async def remove_collaborator(note_id: str, request: Request):
    user = await get_current_user(request)
    if AUTH_REQUIRED and not user:
        return JSONResponse({'error': 'Authentication required'}, status_code=401)
    note = await asyncio.to_thread(database.get_note, note_id)
    if not note:
        return JSONResponse({'error': 'Note not found'}, status_code=404)
    if AUTH_REQUIRED and user != note['owner']:
        return JSONResponse({'error': 'Only owner can manage collaborators'}, status_code=403)
        
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({'error': 'Invalid body'}, status_code=400)
        
    target_user = data.get('username', '').strip()
    await asyncio.to_thread(database.remove_collaborator, note_id, target_user)
    return {'removed': target_user}

# Image Upload & Serve
@app.post('/api/upload')
@app.put('/api/upload')
async def upload_image(request: Request):
    data = await request.body()
    if not data:
        return JSONResponse({'error': 'No file content received'}, status_code=400)
        
    images_dir = './storage/images'
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(images_dir, filename)
    
    with open(filepath, 'wb') as f:
        f.write(data)
        
    return {'url': f'/images/{filename}'}

@app.get('/images/{filename}')
async def serve_image(filename: str):
    safe_filename = os.path.basename(filename)
    filepath = os.path.join('./storage/images', safe_filename)
    if not os.path.isfile(filepath):
        return JSONResponse({'error': 'Image not found'}, status_code=404)
    return FileResponse(filepath)

# WebSocket Real-Time Endpoint
@app.websocket('/ws/notes/{note_id}')
async def websocket_notes_endpoint(websocket: WebSocket, note_id: str):
    await ws_manager.connect(note_id, websocket)
    try:
        while True:
            # Keep connection open & receive any incoming message
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(note_id, websocket)
    except Exception:
        ws_manager.disconnect(note_id, websocket)


def run_server(port=PORT, host=HOST):
    """Launch high-concurrency Uvicorn server"""
    print("\n" + "="*60)
    print("=== High-Performance Web Notepad Server ===")
    print(f"Engine: FastAPI + Uvicorn + SQLite (WAL Mode) + WebSockets")
    print(f"Address: http://localhost:{port}")
    print(f"Authentication: {'ENABLED' if AUTH_REQUIRED else 'DISABLED'}")
    if AUTH_REQUIRED:
        print(f"Default Password: {DEFAULT_PASSWORD}")
    print("="*60 + "\n")
    
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == '__main__':
    run_server()
