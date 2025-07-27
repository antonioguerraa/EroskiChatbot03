# 🚀 Deployment Guide for EroskiChatbot

## ✅ Pre-deployment Test Results

The system has been tested with the query: **"¿Cuál es un consejo para usar la balanza?"**

Results:
- ✅ RAG search working correctly
- ✅ Found 5 relevant results about balance maintenance tips
- ✅ Top result (similarity: 0.644) contains "CONSEJOS DE MANTENIMIENTO Y CUIDADO"
- ✅ Supabase connection working
- ✅ Azure OpenAI embeddings working

## 📋 Deployment Steps

### 1. Push to GitHub
```bash
git push origin modifications_antonio
```

### 2. Deploy on Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Connect your GitHub repository
4. Select branch: `modifications_antonio`
5. Render will detect `render.yaml` automatically

### 3. Environment Variables

Set these in Render dashboard under "Environment":

#### 🗄️ Database (Supabase)
```
DB_HOST=db.ussymmxvlpbtqzarztfi.supabase.co
DB_PASSWORD=Mes001mes001
SUPABASE_DB_STRING=postgresql://postgres:Mes001mes001@db.ussymmxvlpbtqzarztfi.supabase.co:5432/postgres
SUPABASE_POOLER_STRING=postgresql://postgres.ussymmxvlpbtqzarztfi:Mes001mes001@aws-0-eu-west-3.pooler.supabase.com:6543/postgres
```

#### 🤖 Azure OpenAI
```
LLM_AZURE_OPENAI_API_KEY=<your-api-key>
LLM_AZURE_OPENAI_ENDPOINT=https://ai-eroski436893415684.cognitiveservices.azure.com
LLM_AZURE_DEPLOYMENT_NAME=gpt-4o
LLM_AZURE_EMBEDDING_DEPLOYMENT=rag-eroski-embedding
```

#### 🔗 App URL
```
PUBLIC_URL=https://your-app-name.onrender.com
```

### 4. Deploy

Click **Create Web Service** and wait for deployment (~5-10 minutes)

## 🧪 Testing the Deployment

Once deployed, test with:

1. Go to: `https://your-app-name.onrender.com`
2. Login: `admin` / `eroski2024`
3. Conversation flow:
   ```
   You: Soy Juan de la tienda de Bilbao
   Bot: [Identifies you]
   You: ¿Cuál es un consejo para usar la balanza?
   Bot: [Should return maintenance tips from the manual]
   ```

## 📊 Expected Results

The bot should return information about:
- Balance maintenance tips (CONSEJOS DE MANTENIMIENTO)
- Proper usage guidelines
- What not to do with the balance
- Cleaning recommendations

## ⚠️ Important Notes

- **Free Tier**: App sleeps after 15 mins of inactivity
- **Wake Time**: First request takes ~30 seconds
- **Logs**: Check Render dashboard for real-time logs
- **Errors**: If app crashes, check environment variables first

## 🔧 Troubleshooting

If the app doesn't work:

1. **Check Logs** in Render dashboard
2. **Verify Environment Variables** are all set
3. **Check Supabase Connection**: Ensure pooler URL is used
4. **Test Locally First** with same environment variables

## 📞 Support

For issues:
- Check Render logs
- Verify all environment variables
- Ensure branch `modifications_antonio` is deployed
- Database has 560 records with embeddings