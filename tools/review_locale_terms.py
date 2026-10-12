"""Reviewed recruitment terminology layered over draft machine translations."""
import json
from pathlib import Path

DIRECTORY=Path(__file__).resolve().parents[1]/'Locales'
ENGLISH={
    ' из ':' of ', 'Загружено: ':'Loaded: ', 'Отправлено':'Sent',
    'Залогированные прохождения':'Logged runs', 'Прохождения':'Runs',
    'В группе недостаточно свободных мест':'Not enough free slots in the group',
    'Введите Имя-Сервер в поле слева.\nЕсли профиль уже открыт, таблица останется прежней.':'Enter Name-Realm in the field on the left.\nIf this profile is already open, the table will stay unchanged.',
    'Данные выбранной заявки недоступны':'The selected application is unavailable',
    'Логи: только прохождения, доступные WCL; отсутствие данных не означает плохую игру.':'Only runs available on WCL are included. Missing logs do not imply poor performance.',
    'Нажмите |cffffd100Ctrl+C|r, чтобы начать загрузку.\nПомощник получит запрос и подготовит логи.':'Press |cffffd100Ctrl+C|r to send the request.\nThe companion will fetch the logs.',
    'Нажмите «Загрузить M+ логи». Локальный помощник должен быть запущен.':'Click "Load M+ logs". The local companion must be running.',
    'Получить ответ (Ctrl+V)':'Receive logs (Ctrl+V)',
    'Не получен результат для всех кандидатов':'The response is missing results for some applicants',
    'Неизвестная строка импорта; строка ':'Unknown import record; line ',
    'Нет прав на приглашение':'You do not have permission to invite',
    'Объявление закрыто':'The listing is closed',
    'Окно сбора группы ещё не загружено':'The applicant viewer is not loaded yet',
    'Ответ ещё не получен. Нажмите Ctrl+V позже.':'No response yet. Try Ctrl+V again in a moment.',
    'Отсутствует обязательное поле':'A required field is missing',
    'Последняя загрузка: ':'Last loaded: ',
    '  /  Последняя загрузка: ':'  /  Last loaded: ',
    '\nПоследняя дата загрузки - ':'\nLast loaded on ',
    'Приглашение выбранного кандидата':'Invite the selected applicant',
    'Приглашение доступно вне боя':'You can invite outside combat',
    'Запрос доступен вне боя':'Requests are available outside combat',
    'Список кандидатов доступен вне боя':'The applicant list is available outside combat',
    'Сводка открыта вне списка заявок':'This profile was opened outside the applicant list',
    'Сохранён кеш. ':'Showing cached data. ',
    'Ссылка WCL':'WCL link', 'Ссылка Warcraft Logs':'Warcraft Logs link',
    'Ссылка на логи M+':'M+ logs link',
    'Публичные логи M+ не найдены':'No public M+ logs found',
    'включены':'enabled',
    'Сначала нажмите «1. Подготовить».':'Click "1. Prepare" first.',
    '* Пометка WCL сохранена со скриншота. Общие 162 лога и строки показаны как в источнике.':'* The WCL marker is preserved from the screenshot. The total of 162 runs and individual rows match the source.',
    'В буфере нет ответа MPlusLogs для этого запроса. Нажмите Ctrl+V позже; проверьте помощник.':'The clipboard does not contain a MPlusLogs response for this request. Try Ctrl+V again and check the companion.',
    'Теперь нажмите |cffffd100Ctrl+V|r.\nБез вставки WoW не может получить ответ помощника.':'Press |cffffd100Ctrl+V|r now.\nWoW needs you to paste the companion response.',
    'Ответ ещё не получен. Попробуйте Ctrl+V чуть позже; проверьте, что помощник запущен.':'No response yet. Try Ctrl+V again in a moment and make sure the companion is running.',
}
KEYS=['Логи','Данж','Ключ','Пригласить','Загрузить M+ логи','Обновить M+ логи','Загрузить логи всех (','Получить ответ (Ctrl+V)','Показать профиль','Закрыть','All specs']
COMMON={
 'enUS':['Logs','Dungeon','Key','Invite','Load M+ logs','Update M+ logs','Load all logs (','Receive logs (Ctrl+V)','Show profile','Close','All specs'],
 'deDE':['Logs','Dungeon','Stufe','Einladen','M+-Logs laden','M+-Logs aktualisieren','Alle Logs laden (','Logs empfangen (Ctrl+V)','Profil anzeigen','Schließen','Alle Spezialisierungen'],
 'esES':['Logs','Mazmorra','Nivel','Invitar','Cargar logs de M+','Actualizar logs de M+','Cargar todos los logs (','Recibir logs (Ctrl+V)','Ver perfil','Cerrar','Todas las especializaciones'],
 'esMX':['Logs','Calabozo','Nivel','Invitar','Cargar logs de M+','Actualizar logs de M+','Cargar todos los logs (','Recibir logs (Ctrl+V)','Ver perfil','Cerrar','Todas las especializaciones'],
 'frFR':['Logs','Donjon','Niveau','Inviter','Charger les logs M+','Actualiser les logs M+','Charger tous les logs (','Recevoir les logs (Ctrl+V)','Afficher le profil','Fermer','Toutes les spécialisations'],
 'itIT':['Log','Spedizione','Livello','Invita','Carica i log M+','Aggiorna i log M+','Carica tutti i log (','Ricevi i log (Ctrl+V)','Mostra profilo','Chiudi','Tutte le specializzazioni'],
 'ptBR':['Logs','Masmorra','Nível','Convidar','Carregar logs de M+','Atualizar logs de M+','Carregar todos os logs (','Receber logs (Ctrl+V)','Mostrar perfil','Fechar','Todas as especializações'],
 'koKR':['로그','던전','단수','초대','쐐기 로그 불러오기','쐐기 로그 갱신','모든 로그 불러오기 (','로그 받기 (Ctrl+V)','프로필 보기','닫기','모든 전문화'],
 'zhCN':['日志','地下城','层数','邀请','加载大秘境日志','更新大秘境日志','加载所有日志 (','接收日志 (Ctrl+V)','查看资料','关闭','全部专精'],
 'zhTW':['紀錄','地城','層數','邀請','載入傳奇鑰石紀錄','更新傳奇鑰石紀錄','載入所有紀錄 (','接收紀錄 (Ctrl+V)','檢視資料','關閉','所有專精'],
}
BY_LEVEL={'enUS':'by key level','deDE':'nach Schlüsselsteinstufe','esES':'por nivel de llave',
 'esMX':'por nivel de llave','frFR':'par niveau de clé','itIT':'per livello della Chiave',
 'ptBR':'por nível da pedra-chave','koKR':'쐐기 단수 기준','zhCN':'按钥石层数','zhTW':'依鑰石層數'}
OF={'enUS':' of ','deDE':' von ','esES':' de ','esMX':' de ','frFR':' sur ',
 'itIT':' di ','ptBR':' de ','koKR':' / ','zhCN':' / ','zhTW':' / '}
LAST_LOADED={'enUS':'Last loaded: ','deDE':'Zuletzt geladen: ','esES':'Última carga: ',
 'esMX':'Última carga: ','frFR':'Dernier chargement : ','itIT':'Ultimo caricamento: ',
 'ptBR':'Última atualização: ','koKR':'마지막 불러오기: ','zhCN':'上次加载：','zhTW':'上次載入：'}
INVITE_GROUP={'enUS':'Invite group (','deDE':'Gruppe einladen (','esES':'Invitar al grupo (',
 'esMX':'Invitar al grupo (','frFR':'Inviter le groupe (','itIT':'Invita gruppo (',
 'ptBR':'Convidar grupo (','koKR':'파티 초대 (','zhCN':'邀请队伍 (','zhTW':'邀請隊伍 ('}

def main():
    for locale,terms in COMMON.items():
        path=DIRECTORY/(locale+'.json')
        data=json.loads(path.read_text(encoding='utf-8'))
        if locale=='enUS': data.update(ENGLISH)
        data.update(dict(zip(KEYS,terms)))
        by_level=BY_LEVEL[locale]
        data.update({
            ' / по уровню ключа':' / '+by_level,
            ' по уровню ключа':' '+by_level,
            'DPS / по уровню ключа':'DPS / '+by_level,
            'HPS / по уровню ключа':'HPS / '+by_level,
            'M+ Best % по уровню ключа':'M+ Best % '+by_level,
            ' Best % по уровню ключа':' Best % '+by_level,
            'WCL API: M+ по уровню ключа':'WCL API: M+ '+by_level,
            ' из ':OF[locale],
            'Последняя загрузка: ':LAST_LOADED[locale],
            '  /  Последняя загрузка: ':'  /  '+LAST_LOADED[locale],
            'Пригласить группу (':INVITE_GROUP[locale],
        })
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
