// Implementação do servidor (Node.js com Express)
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const bodyParser = require('body-parser');
const mercadopago = require('mercadopago');

const app = express();
const PORT = 8000;

// Configurações
app.use(cors());
app.use(bodyParser.json());

// Arquivo de e-mails
const EMAILS_FILE = path.join(__dirname, 'emails.json');

// Configurar MercadoPago - substitua com sua credencial de acesso
mercadopago.configure({
  access_token: 'TEST-0000000000000000-000000-00000000000000000000000000000000-000000000'
});

// Função para ler o arquivo de e-mails
function readEmailsFile() {
  try {
    if (fs.existsSync(EMAILS_FILE)) {
      const data = fs.readFileSync(EMAILS_FILE, 'utf8');
      return JSON.parse(data);
    }
    return { users: [] };
  } catch (error) {
    console.error('Erro ao ler arquivo de e-mails:', error);
    return { users: [] };
  }
}

// Função para salvar no arquivo de e-mails
function saveEmailsFile(data) {
  try {
    fs.writeFileSync(EMAILS_FILE, JSON.stringify(data, null, 2), 'utf8');
    return true;
  } catch (error) {
    console.error('Erro ao salvar arquivo de e-mails:', error);
    return false;
  }
}

// Verificar se o e-mail já existe
app.post('/check-email', (req, res) => {
  const { email } = req.body;
  
  if (!email) {
    return res.status(400).json({ 
      exists: false, 
      message: 'E-mail não fornecido' 
    });
  }
  
  const emailsData = readEmailsFile();
  const user = emailsData.users.find(u => u.email.toLowerCase() === email.toLowerCase());
  
  if (user) {
    return res.json({ 
      exists: true, 
      user: {
        email: user.email,
        fichas: user.fichas || 0
      }
    });
  } else {
    return res.json({ exists: false });
  }
});

// Registrar novo e-mail
app.post('/register-email', (req, res) => {
  const { email, fichas = 0 } = req.body;
  
  if (!email) {
    return res.status(400).json({ 
      status: 'error', 
      message: 'E-mail não fornecido' 
    });
  }
  
  const emailsData = readEmailsFile();
  
  // Verificar se o e-mail já existe
  const existingUser = emailsData.users.find(u => u.email.toLowerCase() === email.toLowerCase());
  
  if (existingUser) {
    return res.status(400).json({ 
      status: 'error', 
      message: 'E-mail já registrado' 
    });
  }
  
  // Adicionar novo usuário
  emailsData.users.push({
    email,
    fichas,
    dataRegistro: new Date().toISOString()
  });
  
  if (saveEmailsFile(emailsData)) {
    return res.json({ 
      status: 'success', 
      message: 'E-mail registrado com sucesso' 
    });
  } else {
    return res.status(500).json({ 
      status: 'error', 
      message: 'Erro ao salvar os dados' 
    });
  }
});

// Criar um pagamento no Mercado Pago
app.post('/create-payment', async (req, res) => {
  const { email, product, quantity = 1 } = req.body;
  
  if (!email || !product) {
    return res.status(400).json({ 
      status: 'error', 
      message: 'Dados incompletos' 
    });
  }
  
  // Configurar o produto (ficha)
  const items = [{
    title: 'Ficha DocIaPocket',
    description: 'Crédito para uso no DocIaPocket',
    quantity: parseInt(quantity),
    currency_id: 'BRL',
    unit_price: 50.00 // Valor em reais
  }];
  
  try {
    // Criar preferência de pagamento
    const preference = {
      items,
      payer: {
        email
      },
      back_urls: {
        success: `http://localhost:8000/payment-success?email=${email}`,
        failure: `http://localhost:8000/payment-failure?email=${email}`,
        pending: `http://localhost:8000/payment-pending?email=${email}`
      },
      auto_return: 'approved',
      external_reference: email,
      notification_url: `http://localhost:8000/mercadopago-webhook`
    };
    
    const response = await mercadopago.preferences.create(preference);
    
    res.json({ 
      status: 'success', 
      checkoutUrl: response.body.init_point
    });
  } catch (error) {
    console.error('Erro ao criar pagamento:', error);
    res.status(500).json({ 
      status: 'error', 
      message: 'Erro ao processar pagamento' 
    });
  }
});

// Webhook para notificações do Mercado Pago
app.post('/mercadopago-webhook', async (req, res) => {
  const { id, topic } = req.query;
  
  if (topic === 'payment') {
    try {
      // Obter detalhes do pagamento
      const payment = await mercadopago.payment.findById(id);
      
      if (payment.body.status === 'approved') {
        const email = payment.body.external_reference;
        const quantity = payment.body.additional_info.items.reduce((total, item) => {
          return total + item.quantity;
        }, 0);
        
        // Adicionar fichas ao usuário
        const emailsData = readEmailsFile();
        const userIndex = emailsData.users.findIndex(u => u.email.toLowerCase() === email.toLowerCase());
        
        if (userIndex !== -1) {
          // Usuário existente
          emailsData.users[userIndex].fichas = (emailsData.users[userIndex].fichas || 0) + quantity;
          
          // Adicionar registro de transação
          if (!emailsData.users[userIndex].transacoes) {
            emailsData.users[userIndex].transacoes = [];
          }
          
          emailsData.users[userIndex].transacoes.push({
            tipo: 'compra',
            quantidade: quantity,
            data: new Date().toISOString(),
            pagamentoId: id
          });
          
          saveEmailsFile(emailsData);
        }
      }
      
      res.status(200).end();
    } catch (error) {
      console.error('Erro ao processar webhook:', error);
      res.status(500).end();
    }
  } else {
    res.status(200).end();
  }
});

// Usar uma ficha
app.post('/use-token', (req, res) => {
  const { email } = req.body;
  
  if (!email) {
    return res.status(400).json({ 
      success: false, 
      message: 'E-mail não fornecido' 
    });
  }
  
  const emailsData = readEmailsFile();
  const userIndex = emailsData.users.findIndex(u => u.email.toLowerCase() === email.toLowerCase());
  
  if (userIndex === -1) {
    return res.status(404).json({ 
      success: false, 
      message: 'Usuário não encontrado' 
    });
  }
  
  // Verificar se o usuário tem fichas suficientes
  if (!emailsData.users[userIndex].fichas || emailsData.users[userIndex].fichas < 1) {
    return res.status(400).json({ 
      success: false, 
      message: 'Fichas insuficientes' 
    });
  }
  
  // Decrementar ficha
  emailsData.users[userIndex].fichas--;
  
  // Adicionar registro de uso
  if (!emailsData.users[userIndex].transacoes) {
    emailsData.users[userIndex].transacoes = [];
  }
  
  emailsData.users[userIndex].transacoes.push({
    tipo: 'uso',
    quantidade: 1,
    data: new Date().toISOString()
  });
  
  if (saveEmailsFile(emailsData)) {
    return res.json({ 
      success: true, 
      remainingTokens: emailsData.users[userIndex].fichas 
    });
  } else {
    return res.status(500).json({ 
      success: false, 
      message: 'Erro ao salvar os dados' 
    });
  }
});

// Rotas para callbacks do Mercado Pago
app.get('/payment-success', (req, res) => {
  res.send(`
    <html>
      <head>
        <title>Pagamento Concluído</title>
        <style>
          body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
          .success { color: green; }
          button { padding: 10px 20px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer; }
        </style>
      </head>
      <body>
        <h1 class="success">Pagamento Concluído com Sucesso!</h1>
        <p>Suas fichas foram adicionadas à sua conta.</p>
        <button onclick="window.close()">Fechar</button>
      </body>
    </html>
  `);
});

app.get('/payment-failure', (req, res) => {
  res.send(`
    <html>
      <head>
        <title>Pagamento Não Concluído</title>
        <style>
          body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
          .failure { color: red; }
          button { padding: 10px 20px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer; }
        </style>
      </head>
      <body>
        <h1 class="failure">Pagamento Não Concluído</h1>
        <p>Houve um problema com seu pagamento. Por favor, tente novamente.</p>
        <button onclick="window.close()">Fechar</button>
      </body>
    </html>
  `);
});

app.get('/payment-pending', (req, res) => {
  res.send(`
    <html>
      <head>
        <title>Pagamento Pendente</title>
        <style>
          body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
          .pending { color: orange; }
          button { padding: 10px 20px; background: #ff9800; color: white; border: none; border-radius: 4px; cursor: pointer; }
        </style>
      </head>
      <body>
        <h1 class="pending">Pagamento Pendente</h1>
        <p>Seu pagamento está sendo processado. As fichas serão adicionadas quando o pagamento for confirmado.</p>
        <button onclick="window.close()">Fechar</button>
      </body>
    </html>
  `);
});

// Iniciar servidor
app.listen(PORT, () => {
  console.log(`Servidor rodando na porta ${PORT}`);
  
  // Criar arquivo de e-mails se não existir
  if (!fs.existsSync(EMAILS_FILE)) {
    saveEmailsFile({ users: [] });
    console.log('Arquivo de e-mails criado.');
  }
});
