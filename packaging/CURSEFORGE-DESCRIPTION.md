# MPlusLogs

Use MPlusLogs to check Mythic+ Warcraft Logs while putting a group together.

The addon adds a **Logs** column to your Group Finder applications. Left-click a player's number in that column to open their dungeon table: DPS/HPS, Best % and Median %, key levels and logged-run counts. You can switch between specializations and copy their Warcraft Logs link from the same window.

## Getting started

WoW addons cannot fetch data from websites directly. **MPlusLogs Companion** is a Windows app that gets the requested data from Warcraft Logs and passes it back to the addon through your clipboard.

WITHOUT COMPANION INSTALLED AND RUNNING, THE ADDON CANNOT LOAD NEW LOG DATA.

1. Install the addon with CurseForge and [download the recommended Companion installer for Windows 10/11 x64](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe). Run **MPlusLogs-Companion-Setup.exe**.

    Alternatively, download the [portable version in ZIP](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Portable.zip), extract the entire folder and run **MPlusLogs-Companion.exe**. Keep the **_internal** folder beside the EXE. Both links always provide the current release.

    Do not put Companion inside an individual addon folder such as **AddOns\\MPlusLogs**: updating that addon can remove Companion's files. The **AddOns** folder itself or a separate Companion folder is fine. The installer recommends **%LOCALAPPDATA%\\Programs\\MPlusLogs Companion** and lets you choose a folder again when reinstalling.
2. Start Companion and choose **Set up personal API**. The built-in guide will help you:
    - create your Warcraft Logs API client;
    - paste its **Client ID**;
    - authorize access in your browser.

    **Couldn't connect your personal API?** Choose **Use shared API** in Companion and sign in through Warcraft Logs. Everyone using this option shares the same request allowance, which can run out quickly when many people load logs. We recommend switching to your personal API when you can.

3. In WoW, when forming a Mythic+ group, a **Load all logs** button will appear above the application list.
4. Press **Ctrl+C** in the addon window and wait for Companion's sound: it means the reply is ready. Sound is on by default; Companion can stay in the tray.
    - **Without sound:** before pressing **Ctrl+V**, check that Companion says **“The reply is on the clipboard. Return to WoW and press Ctrl+V.”**
5. Once the reply is ready, press **Ctrl+V** in the same addon window. The loaded results will appear in the **Logs** column.

If Companion says the clipboard changed, click **Copy last reply** there, then paste it into WoW with **Ctrl+V**.

You can also use `/mpl`: in a party it opens your group's logs; outside a party it opens your target's logs, or your own if no player is targeted.

## A few things to know

- Both Companion versions support updates from the app: the installed version uses Setup; the portable version downloads a ZIP and replaces its files automatically, restoring the previous version if replacement or the new version's self-test fails. Keep Companion updated so it supports new addon requests.
- Both versions keep login and settings in AppData and support optional startup with Windows or WoW Retail. After manually moving the portable folder, enable startup again from its new location.
- **Update M+ logs** requests fresh Warcraft Logs data once five minutes have passed since the last successful fetch for that character and specialization. Reading cached data or loading other players does not restart this timer.
- Saved data stays between sessions. **Last loaded** is the date the data was fetched, not the date a key was completed. Stale data is shown in grey.
- Only runs available to Warcraft Logs are included. Missing logs are shown as unavailable; percentiles do not measure survival, interrupts or mechanics.
- Companion processes only MPlusLogs clipboard requests. Other clipboard text is not sent to Warcraft Logs.

Addon settings are in WoW under **Options → AddOns → MPlusLogs**. The addon follows your WoW client language. Companion's language can be changed in **Settings → Language**.

Questions or ideas? Join us on [Discord](https://discord.gg/URUukHCUW).

[Source and issue tracker](https://github.com/indrih17/MPlusLogs).

***

## MPlusLogs

С помощью этого аддона вы можете посмотреть логи Mythic+ при наборе группы.

В списке заявок появится колонка **«Логи»**. Нажмите левой кнопкой по числу рядом с игроком в этой колонке — откроется таблица по подземельям: DPS/HPS, Best % и Median %, уровни ключей и число записанных прохождений. Там же можно переключать специализации и скопировать ссылку на Warcraft Logs.

### Как начать

Аддоны WoW не могут сами запрашивать данные с сайтов. Для этого нужен **MPlusLogs Companion** — помощник для Windows. Он получает нужные логи из Warcraft Logs и передаёт их аддону через буфер обмена.

БЕЗ УСТАНОВЛЕННОГО И ЗАПУЩЕННОГО COMPANION АДДОН НЕ СМОЖЕТ ЗАГРУЗИТЬ НОВЫЕ ЛОГИ.

1. Установите аддон через CurseForge и [скачайте рекомендуемый установщик Companion для Windows 10/11 x64](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Setup.exe). Запустите **MPlusLogs-Companion-Setup.exe**.

    Также доступна [portable версия в ZIP](https://github.com/indrih17/MPlusLogs/releases/download/companion-channel/MPlusLogs-Companion-Portable.zip): распакуйте папку целиком и запустите **MPlusLogs-Companion.exe**, оставив папку **_internal** рядом с EXE. Обе ссылки всегда ведут на текущую версию.

    Не размещайте Companion внутри папки отдельного аддона, например **AddOns\\MPlusLogs**: обновление этого аддона может удалить файлы Companion. Сама папка **AddOns** или отдельная папка Companion подходят. Установщик рекомендует **%LOCALAPPDATA%\\Programs\\MPlusLogs Companion** и позволяет заново выбрать папку при переустановке.
2. Запустите Companion и выберите **«Подключить личный API»**. Встроенная инструкция поможет:
    - создать API-клиент Warcraft Logs;
    - вставить его **Client ID**;
    - подтвердить доступ в браузере.

    **Не получилось подключить личный API?** Выберите в Companion **«Использовать общий API»** и авторизуйтесь через Warcraft Logs. Лимит запросов этого API делят все пользователи — при большой нагрузке он может быстро закончиться. Поэтому рекомендуем по возможности перейти на личный API.

3. В WoW при формировании группы для М+ над списком заявок появится кнопка **«Загрузить логи всех»**.
4. В окне аддона нажмите **Ctrl+C** и дождитесь звукового сигнала Companion — он означает, что ответ готов. Звук включён по умолчанию; помощник может оставаться в трее.
    - **Без звука:** перед нажатием **Ctrl+V** дождитесь в окне Companion сообщения **«Ответ в буфере. Вернитесь в WoW и нажмите Ctrl+V»**.
5. Когда ответ готов, нажмите **Ctrl+V** в том же окне аддона. Загруженные результаты появятся в колонке **«Логи»**.

Если Companion сообщает, что буфер изменился, нажмите в нём **«Скопировать последний ответ»**, затем вставьте его в WoW через **Ctrl+V**.

Можно также воспользоваться `/mpl`: в пати команда открывает логи участников группы, а вне пати — выбранного игрока или ваши, если игрок не выбран.

### Полезно знать

- Оба варианта Companion поддерживают обновление из программы: установленная версия обновляется через Setup; portable версия скачивает ZIP и автоматически заменяет свои файлы. При ошибке замены или самопроверки новой версии восстанавливается предыдущая. Обновляйте Companion, чтобы он поддерживал новые запросы аддона.
- Оба варианта сохраняют вход и настройки в AppData и поддерживают автозапуск с Windows или WoW Retail. После ручного переноса папки portable включите автозапуск заново из нового расположения.
- Кнопка **«Обновить М+ логи»** запрашивает свежие данные Warcraft Logs, если с последней успешной загрузки для этого персонажа и специализации прошло пять минут. Чтение кэша и загрузка других игроков не запускают этот таймер заново.
- Загруженные данные сохраняются между сессиями. **«Последняя загрузка»** — дата получения данных, а не прохождения ключа. Устаревшие данные показаны серым.
- В статистику попадают только прохождения, доступные Warcraft Logs. Если логов нет, это видно в окне. Проценты не оценивают выживание, прерывания и выполнение механик.
- Companion обрабатывает только запросы MPlusLogs из буфера обмена. Другой текст не отправляется в Warcraft Logs.

Настройки аддона находятся в WoW: **«Параметры → Модификации → MPlusLogs»**. Аддон использует язык вашего клиента WoW. Язык Companion можно поменять в **«Настройки → Язык»**.

Есть вопрос или идея? Заходите в [Discord](https://discord.gg/URUukHCUW).

[Исходный код и сообщения об ошибках](https://github.com/indrih17/MPlusLogs).
