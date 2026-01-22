# Weekly - Dashboard de Performance de Carteiras

Dashboard interativo para análise de performance de carteiras de investimento.


### Passo a Passo

#### 1. Criar repositório no GitHub
```bash
git init
git add weekly.py requirements.txt .gitignore .streamlit/
git commit -m "Initial commit"
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

#### 2. Configurar Streamlit Community Cloud
1. Acesse [share.streamlit.io](https://share.streamlit.io)
2. Clique em "New app"
3. Conecte seu repositório GitHub
4. Configure:
   - **Repository**: SEU_USUARIO/SEU_REPOSITORIO
   - **Branch**: main
   - **Main file path**: weekly.py
5. Clique em "Advanced settings" (opcional)
6. Configure secrets (se necessário):
   ```toml
   [api]
   username = "seu_usuario"
   password = "sua_senha"
   ```
7. Clique em "Deploy!"

### 📋 Dependências
- streamlit
- pandas
- numpy
- requests
- plotly
- yfinance
- pandas-market-calendars

### 🔒 Secrets
Se o app usar credenciais de API, adicione no Streamlit Cloud:
1. No dashboard do app, clique em "⋮" (três pontos)
2. Vá em "Settings"
3. Na aba "Secrets", cole o conteúdo do secrets.toml

### 🛠️ Desenvolvimento Local
```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar aplicação
streamlit run weekly.py
```

### 📝 Estrutura do Projeto
```
├── weekly.py              # Aplicação principal
├── requirements.txt       # Dependências Python
├── .gitignore            # Arquivos ignorados pelo Git
└── .streamlit/
    ├── config.toml       # Configurações do Streamlit
    └── secrets.toml.example  # Exemplo de secrets
```

## 📊 Funcionalidades
- Dashboard de Performance
- Análise por Categoria
- Gráficos Interativos
- Histórico Mensal com Heatmaps
- Cálculo de métricas (Retorno, Volatilidade, Sharpe, Max Drawdown)
- Comparação com benchmarks (CDI, Ibovespa, IFIX)
