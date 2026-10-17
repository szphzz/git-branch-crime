FROM python:3.13-slim

WORKDIR /streamlit

COPY * ./

RUN pip install -r requirements.txt

EXPOSE 8501

CMD streamlit run hw4.py --server.address=0.0.0.0 --server.port=8501