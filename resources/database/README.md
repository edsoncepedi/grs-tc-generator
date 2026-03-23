[English Version](#english-version) | [Versão em Português](#versão-em-português)

---

## English Version

# Database Configuration

This directory contains the scripts and configurations for the TC Generator's PostgreSQL database.

## Database Structure

The database contains the following main tables:

- `satellites`: Stores information about the satellites
- `operators`: Stores information about the system operators
- `telecommands`: Stores the commands sent to the satellites
- `execution_logs`: Stores execution logs of the commands

## Configuration

1. Ensure PostgreSQL is installed and running
2. Configure the environment variables in the `.env` file at the root of the project:
   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=tc_generator
   DB_USER=root
   DB_PASSWORD=root
   ```

## Database Initialization

To create and populate the database, run the following command:

```bash
# Make the script executable (only the first time)
chmod +x database/script_init_db.py

# Run the initialization script
python database/script_init_db.py
```

## Accessing the Database

### Using psql (command line)

```bash
psql -h localhost -U root -d tc_generator
```

### Using Python

```python
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)

# Query example
with conn.cursor() as cur:
    cur.execute("SELECT * FROM satellites")
    for row in cur.fetchall():
        print(row)

conn.close()
```

## Useful Views

The database includes the following views:

- `vw_recent_telecommands`: Shows recent commands with satellite and operator information

## Useful Functions

- `get_satellite_command_stats(days_interval)`: Returns command statistics per satellite

## Migrations

To make changes to the database schema, follow these steps:

1. Create a new migration file in `database/migrations/` with the format `YYYYMMDD_migration_name.sql`
2. Add the necessary SQL commands for the migration
3. Update the main schema (`schema.sql`) with the changes

## Backup and Restore

### Backup

```bash
pg_dump -h localhost -U root -d tc_generator > backup_$(date +%Y%m%d).sql
```

### Restore

```bash
psql -h localhost -U root -d tc_generator < backup_20231119.sql
```

## Troubleshooting

- **Connection error**: Check if PostgreSQL is running and if the credentials in the `.env` are correct
- **Permission denied**: Ensure the database user has the necessary permissions
- **Foreign key error**: Verify if data is being inserted in the correct order (referenced tables first)

---

## Versão em Português

# Configuração do Banco de Dados

Este diretório contém os scripts e configurações para o banco de dados PostgreSQL do TC Generator.

## Estrutura do Banco de Dados

O banco de dados contém as seguintes tabelas principais:

- `satellites`: Armazena informações sobre os satélites
- `operators`: Armazena informações sobre os operadores do sistema
- `telecommands`: Armazena os comandos enviados para os satélites
- `execution_logs`: Armazena logs de execução dos comandos

## Configuração

1. Certifique-se de que o PostgreSQL está instalado e em execução
2. Configure as variáveis de ambiente no arquivo `.env` na raiz do projeto:
   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=tc_generator
   DB_USER=root
   DB_PASSWORD=root
   ```

## Inicialização do Banco de Dados

Para criar e popular o banco de dados, execute o seguinte comando:

```bash
# Torna o script executável (apenas na primeira vez)
chmod +x database/script_init_db.py

# Executa o script de inicialização
python database/script_init_db.py
```

## Acessando o Banco de Dados

### Usando psql (linha de comando)

```bash
psql -h localhost -U root -d tc_generator
```

### Usando Python

```python
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)

# Exemplo de consulta
with conn.cursor() as cur:
    cur.execute("SELECT * FROM satellites")
    for row in cur.fetchall():
        print(row)

conn.close()
```

## Visualizações Úteis

O banco de dados inclui as seguintes visualizações:

- `vw_recent_telecommands`: Mostra os comandos recentes com informações de satélite e operador

## Funções Úteis

- `get_satellite_command_stats(days_interval)`: Retorna estatísticas de comandos por satélite

## Migrações

Para fazer alterações no esquema do banco de dados, siga estes passos:

1. Crie um novo arquivo de migração em `database/migrations/` com o formato `YYYYMMDD_nome_da_migracao.sql`
2. Adicione os comandos SQL necessários para a migração
3. Atualize o esquema principal (`schema.sql`) com as alterações

## Backup e Restauração

### Backup

```bash
pg_dump -h localhost -U root -d tc_generator > backup_$(date +%Y%m%d).sql
```

### Restauração

```bash
psql -h localhost -U root -d tc_generator < backup_20231119.sql
```

## Solução de Problemas

- **Erro de conexão**: Verifique se o PostgreSQL está em execução e se as credenciais no `.env` estão corretas
- **Permissões negadas**: Certifique-se de que o usuário do banco de dados tem as permissões necessárias
- **Erro de chave estrangeira**: Verifique se os dados estão sendo inseridos na ordem correta (tabelas referenciadas primeiro)