# HackMTY x Banorte — Especificación del Proyecto

## 1. Visión del producto

Estamos construyendo una aplicación financiera inteligente para PyMEs, concebida como una experiencia **by Banorte**.

La idea central es que Banorte ya cuenta con una relación de confianza con el negocio y acceso autorizado a parte de su información financiera. Nuestra propuesta es construir una capa de inteligencia encima de esa infraestructura para transformar movimientos bancarios, CFDIs y contexto financiero en:

1. contabilidad entendible,
2. alertas accionables,
3. resolución automática de tareas,
4. recomendaciones y simulaciones financieras.

El producto no debe sentirse como un ERP, software contable tradicional ni un conjunto de módulos.

Debe sentirse como:

> **Un equipo financiero de IA para el dueño de una PyME.**

Los agentes deben ayudar a:

- entender qué está pasando,
- detectar qué está mal,
- resolver problemas,
- tomar mejores decisiones.

---

# 2. Propuesta de valor

El producto convierte información financiera desordenada en acciones claras.

Ejemplo:

```text
Banorte detecta movimiento
        ↓
se consulta información fiscal
        ↓
se busca CFDI asociado
        ↓
se detecta que no existe
        ↓
se genera una alerta
        ↓
el usuario sube el ticket real
        ↓
el agente entra al portal real de facturación
        ↓
obtiene la factura
        ↓
se reconcilia automáticamente
        ↓
se actualizan las finanzas
```

También debe detectar cuentas por cobrar.

Ejemplo:

```text
5 facturas emitidas siguen sin cobro
Total pendiente: $84,500

[Resolver]
```

Al presionar Resolver:

```text
Operator Agent
      ↓
identifica clientes y facturas pendientes
      ↓
obtiene datos de contacto autorizados
      ↓
prepara recordatorios de pago
      ↓
envía automáticamente los correos
      ↓
registra que se realizó el seguimiento
```

Y además:

```text
Usuario:
“¿Puedo contratar a alguien por $20,000 al mes?”
        ↓
Consultor consulta:
- flujo de efectivo
- utilidad
- gastos
- liquidez
        ↓
corre una simulación
        ↓
entrega una recomendación concreta
```

---

# 3. Los 4 agentes

## 3.1 Agente Contador

Responsabilidad:

- obtener movimientos bancarios,
- obtener CFDIs,
- normalizar información,
- conciliar movimientos contra CFDIs,
- detectar facturas emitidas pendientes de cobro,
- generar información financiera estructurada.

Debe producir:

- estado de resultados básico,
- flujo de efectivo,
- balance general simplificado,
- ingresos,
- gastos,
- utilidad,
- efectivo,
- impuesto estimado,
- movimientos sin CFDI,
- cuentas por cobrar,
- movimientos que requieren revisión.

Importante:

El agente no debe “inventar” estados financieros.

La lógica financiera debe ser determinística.

Correcto:

```text
transactions
   ↓
financial engine
   ↓
P&L / cash flow / metrics
   ↓
agent interpretation
```

Incorrecto:

```text
transactions
   ↓
LLM
   ↓
“creo que tu utilidad es…”
```

---

## 3.2 Agente Analista Financiero

Responsabilidad:

Interpretar los resultados financieros y generar alertas útiles.

Ejemplos:

```text
⚠️ 4 gastos no tienen CFDI asociado
```

```text
⚠️ Tienes $84,500 en facturas emitidas que todavía no han sido cobradas
```

```text
⚠️ Tus gastos crecieron 18% mientras que tus ventas solo crecieron 4%
```

```text
⚠️ Tu margen cayó de 21% a 15%
```

Las alertas deben ser accionables.

Ejemplo:

```text
4 gastos necesitan factura
Total: $8,460

[Resolver]
```

Otro ejemplo:

```text
5 facturas pendientes de cobro
Total: $84,500

[Resolver]
```

El analista debe trabajar sobre datos estructurados, no consultar directamente tablas arbitrarias.

---

## 3.3 Agente Operador

Responsabilidad:

Ejecutar tareas financieras y administrativas.

### Caso 1: resolver gastos sin factura

```text
gasto sin factura
      ↓
usuario sube ticket real
      ↓
se extraen datos del ticket
      ↓
se hace match con movimiento Banorte
      ↓
se obtiene perfil fiscal
      ↓
se identifica el portal real de facturación del comercio
      ↓
browser agent navega el portal real
      ↓
llena los datos requeridos
      ↓
usuario confirma antes de una acción final irreversible
      ↓
se solicita/obtiene CFDI
      ↓
se reconcilia
```

El objetivo es que el browser agent se adapte dinámicamente a portales de facturación reales.

No queremos construir portales mock para esta parte.

La demo debe utilizar:

- un ticket real,
- un portal real de facturación,
- un flujo real de navegación.

La implementación debe estar preparada para detenerse si encuentra:

- CAPTCHA,
- autenticación no soportada,
- datos obligatorios faltantes,
- errores del portal.

### Caso 2: cobrar cuentas por cobrar

Cuando el sistema detecta CFDIs emitidos que no tienen un ingreso bancario conciliado, debe tratarlos como posibles cuentas por cobrar.

Ejemplo:

```text
Tienes 5 facturas pendientes de cobro
Total: $84,500

[Resolver]
```

Al presionar Resolver:

```text
Operator Agent
      ↓
get_open_receivables()
      ↓
get_customer_contact()
      ↓
prepare_payment_reminder()
      ↓
send_payment_reminder_email()
      ↓
guardar seguimiento
```

El correo debe incluir al menos:

- nombre del cliente,
- referencia o UUID de la factura,
- importe pendiente,
- fecha de emisión,
- fecha de vencimiento si existe,
- un mensaje corto y profesional solicitando el pago.

Ejemplo conceptual:

```text
Asunto: Recordatorio de pago — Factura A-1024

Hola, Cliente ABC:

Te recordamos que la factura A-1024 por $18,500 continúa pendiente de pago.

Fecha de emisión: 12/08/2026
Importe pendiente: $18,500

Agradecemos tu apoyo para realizar el pago o compartirnos el estatus correspondiente.

Saludos,
CAFÉ NORTEÑO SA DE CV
```

La aplicación puede enviar estos correos mediante una integración de correo autorizada.

---

## 3.4 Agente Consultor Financiero

Responsabilidad:

Responder preguntas sobre el negocio utilizando información financiera ya procesada.

Ejemplos:

```text
¿Puedo contratar a alguien por $20,000 al mes?
```

```text
¿Puedo pedir un crédito de $400,000?
```

```text
¿Qué gasto me está afectando más?
```

```text
¿Cuánto margen tengo antes de quedarme corto de efectivo?
```

El consultor debe usar tools.

Ejemplo:

```text
get_financial_summary
get_cash_flow
simulate_hiring
```

El modelo interpreta el resultado.

No calcula directamente.

---

# 4. Experiencia de usuario

La aplicación debe ser una sola página.

No queremos:

```text
Dashboard
Contabilidad
Facturación
Reportes
SAT
Créditos
Consultoría
```

Queremos algo más simple:

```text
Buenos días

Tu negocio hoy

Ventas              $482,300
Utilidad             $71,400
Efectivo            $184,200
Impuesto estimado    $32,600
Cuentas por cobrar   $84,500
```

Después:

```text
Necesita tu atención
```

Con alertas.

Ejemplos:

```text
4 gastos necesitan factura
[Resolver]
```

```text
5 facturas están pendientes de cobro
[Resolver]
```

Después:

```text
Lo que deberías saber hoy
```

Y finalmente:

```text
Pregúntame sobre tu negocio...
```

Todo debe suceder sin cambiar constantemente de módulo.

---

# 5. Qué queremos del UX

Queremos:

- una interfaz simple,
- enfocada en el dueño de una PyME,
- métricas fáciles de entender,
- acciones claras,
- copy corto,
- estados de carga visibles,
- sensación de que los agentes están trabajando,
- interfaces dinámicas,
- una sola página,
- resolver problemas sin navegar por menús.

Ejemplo de feedback:

```text
Conectando con Banorte...

✓ 427 movimientos encontrados
✓ 392 CFDIs encontrados
✓ 381 conciliados automáticamente
✓ 5 cuentas por cobrar identificadas

Preparando tu negocio...
```

---

# 6. Qué NO queremos del UX

No queremos:

- un ERP,
- un dashboard con 40 gráficas,
- menús complejos,
- lenguaje contable demasiado técnico,
- módulos separados para todo,
- que el usuario tenga que aprender contabilidad,
- flujos escondidos en 8 pantallas,
- chat como única forma de usar el producto.

La IA debe complementar la interfaz, no sustituirla completamente.

---

# 7. Stack

## Frontend

```text
Next.js
React
TypeScript
Tailwind
shadcn/ui
Recharts
TanStack Query
```

Zustand solo si se necesita.

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
httpx
```

## Base de datos

```text
PostgreSQL
```

Recomendación:

```text
Supabase
```

Para:

- PostgreSQL,
- Storage,
- opcionalmente Auth.

## IA

```text
OpenAI API
Structured Outputs
Tool Calling
Vision
```

No meter LangChain por default.

## MCP

```text
Python MCP SDK
```

## Browser automation

```text
Playwright
```

## Matching

```text
RapidFuzz
Decimal
```

## Email

Puede usarse:

```text
Gmail API
Microsoft Graph
Resend
SendGrid
```

La implementación concreta puede definirse después, pero debe estar abstraída detrás de un `MailProvider`.

## Deploy

```text
Frontend → Vercel
Backend → Railway / Render
DB → Supabase
```

---

# 8. Arquitectura

```text
┌──────────────────────────────────────┐
│            Next.js Web App           │
│                                      │
│ Metrics • Alerts • Actions • Chat    │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│              FastAPI                 │
│                                      │
│ API                                  │
│ Financial Engine                     │
│ Agent Engine                         │
│ MCP                                  │
│ Integrations                         │
└─────────────┬─────────────┬──────────┘
              │             │
              ▼             ▼
        PostgreSQL       OpenAI API
              │
      ┌───────┼─────────────┐
      ▼       ▼             ▼
 Mock Banorte  Mock SAT   Mail Provider
```

Browser flow:

```text
Ticket real
   ↓
Vision
   ↓
Operator Agent
   ↓
Playwright
   ↓
Portal real de facturación
   ↓
CFDI
```

Collections flow:

```text
CFDIs emitidos
   +
movimientos bancarios
        ↓
open receivables
        ↓
Operator Agent
        ↓
Mail Provider
        ↓
recordatorio de pago
```

---

# 9. Principio arquitectónico principal

Separar:

```text
cálculo
```

de:

```text
razonamiento
```

El Financial Engine calcula.

Los agentes interpretan.

El MCP expone capacidades.

La UI presenta resultados.

---

# 10. Mock de Banorte

La aplicación está concebida como una experiencia interna de Banorte.

Para el hackathon, simularemos APIs internas.

No debemos afirmar que estas APIs existen exactamente de esta forma en producción.

Podemos asumir conceptualmente que Banorte tiene acceso autorizado a:

- información del negocio,
- cuentas,
- saldos,
- movimientos,
- productos financieros,
- identidad/autorización.

Mock APIs:

```text
banorte_get_business_profile
banorte_get_accounts
banorte_get_transactions
banorte_get_balance
banorte_get_fiscal_authorization
banorte_get_credit_options
banorte_simulate_business_loan
```

---

# 11. Autorización fiscal

No queremos decir:

> Banorte nos entrega el `.key`, `.cer` y contraseña de e.firma.

Queremos modelarlo como:

```text
Banorte Identity
      ↓
delegated fiscal authorization
      ↓
sat_sync_cfdis
```

La app recibe una autorización lógica.

Ejemplo:

```json
{
  "authorization_id": "fiscal_auth_001",
  "company_id": "company_001",
  "status": "authorized",
  "scopes": [
    "cfdi.read.received",
    "cfdi.read.issued"
  ]
}
```

---

# 12. Mock del SAT

La recuperación de CFDIs será mock.

La estructura de los datos debe ser lo más realista posible.

No queremos:

```json
{
  "merchant": "Costco",
  "price": 3421
}
```

Queremos datos basados en CFDI 4.0.

---

# 13. CFDIs

Preferencia:

Guardar CFDIs mock como XMLs realistas.

```text
seed/
└── cfdis/
    ├── received/
    └── issued/
```

Después:

```text
XML mock
   ↓
parser REAL
   ↓
objeto normalizado
   ↓
PostgreSQL
```

La frontera mock es:

```text
cómo llegó el XML
```

El procesamiento posterior sí debe ser real.

---

# 14. Base de datos

La información mock no debe vivir hardcodeada dentro del código.

Debe vivir como estado real de la aplicación.

Regla:

```text
JSON/XML = seed
PostgreSQL = runtime
```

Tablas principales:

```text
companies
business_profiles
fiscal_authorizations

bank_accounts
transactions

cfdis
transaction_cfdi_matches

accounts_receivable
collection_actions

financial_snapshots
alerts

documents
invoice_requests

customer_contacts

conversations
messages

agent_runs
tool_calls
```

---

# 15. Cuentas por cobrar

Una cuenta por cobrar puede inferirse cuando existe un CFDI emitido de ingreso que todavía no tiene un movimiento bancario asociado que represente su cobro.

Modelo sugerido:

```text
accounts_receivable
────────────────────────
id
company_id
cfdi_id
customer_name
customer_rfc
amount
amount_paid
amount_pending
issued_at
due_date
status
last_reminder_at
created_at
updated_at
```

Estados:

```text
open
partially_paid
paid
overdue
```

Acciones de cobranza:

```text
collection_actions
────────────────────────
id
receivable_id
action_type
recipient
subject
status
sent_at
created_at
```

---

# 16. Contactos de clientes

Para poder cobrar por correo, el sistema necesita un contacto autorizado.

Tabla sugerida:

```text
customer_contacts
────────────────────────
id
company_id
customer_rfc
customer_name
email
phone
created_at
```

La fuente del contacto puede ser:

- datos existentes del negocio,
- CRM,
- directorio interno,
- alta manual.

No asumir que el CFDI siempre incluye un email utilizable.

---

# 17. Reconciliación

Comparar movimientos Banorte contra CFDIs.

No usar IA como primera estrategia.

Usar:

```text
monto
fecha
merchant similarity
```

Ejemplo:

```python
score = (
    amount_score * 0.50
    + date_score * 0.20
    + merchant_score * 0.30
)
```

Thresholds:

```text
>= 0.85 → auto match
0.60–0.85 → review
< 0.60 → unmatched
```

La misma lógica debe ayudar a detectar cuentas por cobrar:

```text
CFDI emitido
   ↓
buscar ingreso bancario asociado
   ↓
si no existe
   ↓
open receivable
```

---

# 18. Financial Engine

Debe ser código determinístico.

Funciones:

```text
generate_income_statement
generate_cash_flow
generate_balance_sheet
calculate_financial_metrics
estimate_taxes
get_open_receivables
calculate_receivables_metrics
simulate_hiring
simulate_loan
```

---

# 19. Browser Agent

Objetivo:

Completar portales reales distintos usando el mismo agente.

Stack:

```text
Playwright
OpenAI
Structured Output
```

Debe recibir:

- URL,
- título,
- elementos interactivos,
- labels,
- roles,
- screenshot opcional.

No usar coordenadas como estrategia principal.

Acciones permitidas:

```text
navigate
fill
click
select
scroll
go_back
finish
request_user_input
```

Reglas:

- no inventar datos,
- detenerse ante CAPTCHA,
- pedir información si falta,
- límite de pasos,
- confirmación antes de acciones externas irreversibles.

No se utilizarán portales mock para demostrar esta capacidad.

---

# 20. MCP

MCP debe ser pequeño y claro.

Tools recomendadas:

## Banking

```text
banorte_get_accounts
banorte_get_transactions
banorte_get_balance
```

## Fiscal

```text
banorte_get_fiscal_authorization
sat_sync_cfdis
sat_get_cfdi
```

## Financial

```text
get_financial_summary
get_cash_flow
get_unmatched_expenses
get_open_receivables
simulate_hiring
simulate_business_loan
```

## Operations

```text
extract_receipt
match_receipt_to_transaction
get_fiscal_profile
prepare_invoice_request
submit_invoice_request
reconcile_cfdi
get_customer_contact
prepare_payment_reminder
send_payment_reminder_email
```

---

# 21. Mail Provider

El envío de recordatorios debe estar abstraído.

```python
class MailProvider:
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str
    ):
        ...
```

Implementaciones posibles:

```text
GmailMailProvider
MicrosoftMailProvider
ResendMailProvider
```

El Operator Agent no debe saber qué proveedor se utiliza.

---

# 22. UI generativa

No queremos:

```text
LLM → JSX arbitrario
```

Queremos:

```text
LLM
 ↓
UI Schema
 ↓
React Component Registry
```

Ejemplos:

```json
{
  "component": "loan_comparison",
  "props": {
    "amount": 400000
  }
}
```

```json
{
  "component": "receivables_resolution",
  "props": {
    "total_pending": 84500,
    "invoices": []
  }
}
```

---

# 23. Flujo principal del demo

```text
Activar equipo financiero
        ↓
movimientos Banorte
        ↓
CFDIs
        ↓
conciliación
        ↓
dashboard
```

Primer problema:

```text
4 gastos necesitan factura
[Resolver]
```

Después:

```text
ticket real
        ↓
visión
        ↓
match con Banorte
        ↓
browser agent
        ↓
portal real
        ↓
CFDI
        ↓
alerta resuelta
```

Segundo problema:

```text
5 facturas pendientes de cobro
[Resolver]
```

Después:

```text
Operator Agent
        ↓
identifica cuentas por cobrar
        ↓
obtiene emails
        ↓
manda recordatorios
        ↓
registra seguimiento
```

Después:

```text
Consultor
        ↓
simulación contratación / crédito
```

---

# 24. Qué es REAL en el hackathon

Queremos que esto sí funcione realmente:

```text
frontend
backend
database
financial engine
CFDI parser
reconciliation
accounts receivable detection
agents
MCP calls
vision extraction
browser agent
navegación en portal real de facturación
email de cobranza
simulations
alerts
dashboard
chat
```

---

# 25. Qué es MOCK

Mockear:

```text
Banorte internal APIs
SAT retrieval
fiscal authorization
credit offers
real banking authentication
```

La facturación mediante navegador no será mock en el flujo principal.

---

# 26. Qué NO queremos construir

No construir:

- SAT production integration,
- Banorte production integration,
- microservices,
- Kubernetes,
- Kafka,
- vector DB,
- RAG complejo,
- mobile app,
- múltiples bancos,
- ERP completo,
- payroll completo,
- contabilidad mexicana fiscalmente exhaustiva,
- cientos de tipos de alertas,
- sistema de permisos enterprise,
- almacenamiento de e.firma en plaintext.

---

# 27. Estructura del repo

```text
hackmty-financial-ai/
│
├── apps/
│   ├── web/
│   └── api/
│
├── seed/
│   ├── company.json
│   ├── accounts.json
│   ├── transactions.json
│   └── cfdis/
│
├── docs/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

Backend:

```text
apps/api/app/
├── api/
├── agents/
├── financial/
├── browser/
├── integrations/
│   ├── banking/
│   ├── sat/
│   ├── invoicing/
│   └── mail/
├── mcp/
├── models/
├── schemas/
└── services/
```

---

# 28. División conceptual de responsabilidades

## Backend / Financial Engine

- FastAPI,
- DB,
- schemas,
- migrations,
- mock Banorte,
- mock SAT,
- CFDI parser,
- reconciliation,
- accounts receivable,
- financial engine,
- simulations.

## Agents / MCP / Browser Agent

- OpenAI integration,
- structured outputs,
- prompts,
- MCP,
- Accountant Agent,
- Analyst Agent,
- Operator Agent,
- Consultant Agent,
- receipt extraction,
- Playwright,
- browser agent,
- email collections workflow.

## Frontend / UX

- Next.js,
- dashboard,
- metrics,
- charts,
- alerts,
- receipt UI,
- browser progress UI,
- collections UI,
- chat,
- loan simulator UI,
- hiring simulator UI,
- polish.

---

# 29. Product positioning

No decir:

> “Reemplazamos al contador.”

Preferir:

> “Automatizamos el trabajo financiero operativo y convertimos información contable en decisiones y acciones para el dueño.”

No decir:

> “Banorte nos da la e.firma por API.”

Preferir:

> “La solución está diseñada para operar dentro del ecosistema Banorte utilizando autorización fiscal delegada e infraestructura interna autorizada.”

No decir:

> “Funciona con todos los portales de facturación.”

Preferir:

> “El browser agent está diseñado para adaptarse dinámicamente a distintos portales reales de facturación.”

---

# 30. One-liner

> **Un equipo financiero de IA by Banorte que convierte movimientos bancarios en contabilidad, alertas, acciones, cobranza y decisiones.**
