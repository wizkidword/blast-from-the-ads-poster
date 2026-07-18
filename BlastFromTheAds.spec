# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts\\social_batch_app.py'],
    pathex=['C:\\Users\\jrock\\Documents\\CODERSCORNER\\CODEX\\blast-from-the-ads-poster\\scripts'],
    binaries=[],
    datas=[],
    hiddenimports=['app_metadata', 'app_paths', 'ai_analysis', 'blast_workflow', 'caption_builder', 'cleanup', 'desktop_requeue', 'desktop_review', 'desktop_settings', 'desktop_status', 'desktop_theme', 'desktop_workflow', 'export_packs', 'manifest_service', 'media_artifacts', 'media_rules', 'media_processing', 'platform_profiles', 'process_inbox_social', 'processing_orchestrator', 'processing_transaction', 'publishing', 'requeue', 'recovery_queue', 'review_queue', 'run_ledger', 'run_history', 'settings_store', 'thumbnails'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BlastFromTheAds',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
