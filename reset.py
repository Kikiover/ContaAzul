import sqlite3
conn = sqlite3.connect('controle.db')
conn.execute("UPDATE clientes SET ultima_sync_pessoas=NULL WHERE id='umbrella'")
conn.commit()
print('OK')