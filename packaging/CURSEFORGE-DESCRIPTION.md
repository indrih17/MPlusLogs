# MPlusLogs

View Mythic+ Warcraft Logs profiles while recruiting a group. MPlusLogs adds DPS and HPS percentiles, logged-run counts, specialization, key levels and data freshness to player panels and group finder tooltips. Right-click an applicant or player to open their full dungeon table and Warcraft Logs link.

## Windows Companion required for fresh data

**[Download MPlusLogs Companion for Windows](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe)** — the current published installer for Windows 10/11 x64. This permanent download link is updated when a new Companion version is released.

Run the downloaded **MPlusLogs-Companion-Setup.exe** and install Companion outside WoW `Interface\AddOns`; use the default installation folder. Python is included. Companion supports all WoW client languages; choose one in **Settings → Language**. Companion checks for updates and offers an **Install update and restart** button when a new version is available.

1. Install this addon with CurseForge.
2. Start the Companion and sign in through Warcraft Logs in your browser.
3. In WoW, open `/mpl` or right-click a group applicant and choose M+ logs.
4. Choose Load M+ logs, press **Ctrl+C**, wait for the Companion response, then press **Ctrl+V** in the addon.

Use `/mpl demo` to preview a fictional profile. `/mpl import` supports manual import. Cached profiles are saved between sessions; profiles older than 24 hours are marked as stale.

## Privacy and limitations

The addon cannot access the internet directly. The Companion processes only MPlusLogs request envelopes from the clipboard and sends the requested character identifiers and filters to Warcraft Logs. Other clipboard text is not sent. It does not read game memory or automate gameplay. Login tokens are protected locally with Windows DPAPI. Autostart and sounds can be configured in Companion Settings.

Percentiles reflect available Warcraft Logs data, not every run a player has completed. Tank DPS is not a measure of survival. Missing data is shown as unavailable, never as a zero percentile.

The addon follows your WoW client language: English, Russian, German, French, Italian, Spanish, Portuguese, Korean and Chinese. Community translation corrections are welcome.

[Source and issue tracker](https://github.com/indrih17/MPlusLogs)

## Community

Join the [MPlusLogs Discord server](https://discord.gg/URUukHCUW) to discuss the addon, ask questions and share feedback.

***

## MPlusLogs

Смотрите логи Mythic+ при наборе группы. MPlusLogs показывает процентили DPS и HPS, число прохождений, специализацию, уровень ключа и дату прохождения ключа в панелях игроков и подсказках списка заявок. Нажмите правой кнопкой по заявке или игроку, чтобы открыть полную таблицу подземелий и ссылку на Warcraft Logs.

### Для загрузки логов обязательно установите и запустите MPlusLogs Companion на Windows

**[Скачать MPlusLogs Companion для Windows](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe)** — установщик актуальной опубликованной версии для Windows 10/11 x64. Эта постоянная ссылка обновляется при выпуске новой версии компаньона.

Запустите скачанный **MPlusLogs-Companion-Setup.exe** и установите Companion вне папки WoW `Interface\AddOns`, оставив предложенную установщиком папку. Python отдельно устанавливать не нужно. Язык можно выбрать в **Settings → Language**. Компаньон проверяет обновления и предлагает кнопку **Install update and restart**, когда доступна новая версия. Войдите в Warcraft Logs через браузер из Companion.

1. Установите аддон через CurseForge.
2. Запустите Companion и войдите в Warcraft Logs через браузер.
3. В WoW откройте `/mpl` или нажмите правой кнопкой по заявке на вступление в группу и выберите логи M+.
4. Выберите «Загрузить M+ логи», нажмите **Ctrl+C**, дождитесь ответа Companion и нажмите **Ctrl+V** в аддоне.

**Без установленного и запущенного Companion онлайн-загрузка логов не работает.**

Команда `/mpl demo` показывает вымышленный профиль. Для ручного импорта используйте `/mpl import`. Профили сохраняются между сессиями; данные старше 24 часов отмечаются как устаревшие.

## Конфиденциальность и ограничения

Аддон не подключается к интернету напрямую. Companion обрабатывает только запросы MPlusLogs из буфера обмена и отправляет Warcraft Logs запрошенные имена персонажей и фильтры. Остальной текст буфера не отправляется. Companion не читает память игры и не автоматизирует игровой процесс. Токены входа защищены Windows DPAPI. Автозапуск и звук настраиваются отдельно.

Процентили основаны на доступных логах Warcraft Logs, а не на всех прохождениях игрока. DPS танка не показывает его выживаемость. Если данных нет, аддон показывает их как недоступные, а не как нулевой процентиль. Язык аддона зависит от языка клиента WoW.

[Github проекта](https://github.com/indrih17/MPlusLogs)

## Сообщество

Обсудить аддон, задать вопрос или оставить отзыв можно в [Discord MPlusLogs](https://discord.gg/URUukHCUW).
