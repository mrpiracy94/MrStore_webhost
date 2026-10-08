<?php
header('Content-Type: text/html; charset=utf-8');
?><!doctype html>
<html lang="pt"><meta charset="utf-8"><title>PHP no ZimaOS</title>
<style>body{font-family:system-ui;margin:12vh auto;max-width:600px;background:#111827;color:white}h1{color:#34d399}</style>
<h1>PHP está a funcionar 🎉</h1>
<p>Versão PHP: <strong><?= htmlspecialchars(PHP_VERSION) ?></strong></p>
<p>Data do servidor: <?= htmlspecialchars(date('Y-m-d H:i:s')) ?></p></html>