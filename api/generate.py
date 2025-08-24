from http.server import BaseHTTPRequestHandler
import json
import os
import base64
from openai import OpenAI

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # OpenAI APIキーの確認
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                self.send_error_response({'error': 'OpenAI APIキーが設定されていません'})
                return
                
            # リクエストデータの読み取り
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error_response({'error': 'リクエストデータが空です'})
                return
                
            post_data = self.rfile.read(content_length)
            
            # マルチパートデータの簡易解析
            # 実際の画像データと設定値を抽出
            image_data = None
            mood = 'カジュアル'
            language = 'japanese_english'
            
            # マルチパートの境界を見つけて画像データを抽出
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in content_type:
                boundary = content_type.split('boundary=')[1]
                parts = post_data.split(f'--{boundary}'.encode())
                
                for part in parts:
                    part_str = part.decode('utf-8', errors='ignore')
                    
                    if b'name="image"' in part and b'Content-Type:' in part:
                        # 画像データ部分を抽出
                        header_end = part.find(b'\r\n\r\n')
                        if header_end != -1:
                            image_data = part[header_end + 4:]
                            # 末尾の改行を除去
                            if image_data.endswith(b'\r\n'):
                                image_data = image_data[:-2]
                    elif b'name="mood"' in part:
                        # mood値を抽出（改善版）
                        header_end = part.find(b'\r\n\r\n')
                        if header_end != -1:
                            mood_data = part[header_end + 4:]
                            if mood_data.endswith(b'\r\n'):
                                mood_data = mood_data[:-2]
                            mood = mood_data.decode('utf-8').strip()
                            print(f"DEBUG: Extracted mood: '{mood}'")
                    elif b'name="language"' in part:
                        # language値を抽出（改善版）
                        header_end = part.find(b'\r\n\r\n')
                        if header_end != -1:
                            lang_data = part[header_end + 4:]
                            if lang_data.endswith(b'\r\n'):
                                lang_data = lang_data[:-2]
                            language = lang_data.decode('utf-8').strip()
                            print(f"DEBUG: Extracted language: '{language}'")
            
            if not image_data:
                self.send_error_response({'error': '画像データが見つかりません'})
                return
            
            # OpenAI クライアント初期化
            try:
                client = OpenAI(api_key=api_key)
            except Exception as init_error:
                # より安全な初期化方法
                import openai
                openai.api_key = api_key
                client = openai
            
            # 画像をBase64エンコード
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # デバッグ情報を追加
            debug_info = {
                'received_mood': mood,
                'received_language': language,
                'image_data_length': len(image_data) if image_data else 0
            }
            
            # 画像解析
            image_description = self.analyze_image(client, base64_image)
            
            # 投稿文生成
            captions = self.generate_captions(client, image_description, mood, language)
            
            # 成功レスポンス
            self.send_success_response({
                'success': True,
                'debug_info': debug_info,
                'image_description': image_description,
                'captions': captions
            })
            
        except Exception as e:
            import traceback
            self.send_error_response({
                'error': f'処理エラー: {str(e)}',
                'traceback': traceback.format_exc()
            })
    
    def analyze_image(self, client, base64_image):
        """OpenAI Vision APIで画像を解析"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "この画像の内容を詳しく分析して、日本語で簡潔に要約してください。人物、物、場所、雰囲気、色彩、構図などを含めて説明してください。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            # フォールバック: 旧APIスタイル
            import openai
            response = openai.ChatCompletion.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "この画像の内容を詳しく分析して、日本語で簡潔に要約してください。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
    
    def generate_captions(self, client, image_description, mood, language):
        """投稿文を生成"""
        
        # 雰囲気に基づく詳細な文体指示
        mood_instructions = {
            "カジュアル": {
                "tone": "親しみやすく、リラックスした口調で。「〜だよね」「〜かも」などの砕けた表現を使用。絵文字は適度に使用。",
                "style": "日常的で自然体な表現",
                "example_words": ["楽しい", "いい感じ", "のんびり", "マイペース"]
            },
            "ユーモラス": {
                "tone": "面白く、笑いを誘う表現で。ダジャレや軽いツッコミ、面白い比喩を含める。絵文字は多めに使用。",
                "style": "コミカルでエンターテイニングな表現",
                "example_words": ["爆笑", "ウケる", "面白すぎ", "笑える", "ツボった"]
            },
            "詩的": {
                "tone": "美しく叙情的な表現で。比喩や擬人法を多用し、感情豊かに。絵文字は控えめで上品に。",
                "style": "文学的で芸術的な表現",
                "example_words": ["美しい", "幻想的", "心に響く", "儚い", "永遠"]
            },
            "クール": {
                "tone": "洗練されたクールな表現で。短文でインパクト重視。無駄な言葉は省いて。絵文字は最小限。",
                "style": "スタイリッシュで都会的な表現",
                "example_words": ["シンプル", "スタイリッシュ", "洗練", "ミニマル"]
            },
            "エモーショナル": {
                "tone": "感情的で心に訴える表現で。内面の気持ちを豊かに表現し、共感を呼ぶ。絵文字で感情を強調。",
                "style": "感動的で心温まる表現",
                "example_words": ["感動", "心温まる", "涙が出そう", "胸がいっぱい", "幸せ"]
            },
            "プロフェッショナル": {
                "tone": "丁寧で品格のある表現で。敬語を適度に使用し、信頼感のある文体。絵文字は控えめ。",
                "style": "ビジネスライクで信頼感のある表現",
                "example_words": ["品質", "丁寧", "信頼", "プロフェッショナル", "こだわり"]
            },
            "フレンドリー": {
                "tone": "温かく親近感のある表現で。「みんな〜」「一緒に〜」など仲間意識を表現。絵文字で親しみやすさを演出。",
                "style": "親しみやすく温かい表現",
                "example_words": ["みんな", "一緒", "仲間", "つながり", "シェア"]
            },
            "ロマンチック": {
                "tone": "甘く優雅な表現で。恋愛的な比喩や美しい形容詞を多用。ハートや花の絵文字を効果的に使用。",
                "style": "ロマンティックで優雅な表現",
                "example_words": ["素敵", "ときめき", "ドキドキ", "優雅", "魅力的"]
            },
            "アーティスティック": {
                "tone": "創造的で芸術的な表現で。独創的な視点や美的センスを表現。色彩や形状の美しさを強調。",
                "style": "芸術的で創造的な表現",
                "example_words": ["芸術", "創造", "美的", "インスピレーション", "表現"]
            },
            "ミニマル": {
                "tone": "シンプルで無駄のない表現で。短文で要点を的確に。絵文字も最小限でスッキリと。",
                "style": "簡潔で洗練された表現",
                "example_words": ["シンプル", "ミニマル", "本質", "純粋", "クリア"]
            },
            "レトロでノスタルジックな言葉で表現": {
                "tone": "懐かしく温かみのある表現で。昔を思わせる言葉遣いや古風な表現を使用。絵文字は使わず、文学的で深みのある文章。",
                "style": "レトロで郷愁を誘う表現",
                "example_words": ["懐かしい", "郷愁", "古き良き", "追憶", "記憶", "温もり", "昔日", "思い出"]
            }
        }
        
        # 選択された雰囲気の指示を取得（デバッグ用ログ追加）
        print(f"DEBUG: Looking for mood '{mood}' in mood_instructions")
        print(f"DEBUG: Available moods: {list(mood_instructions.keys())}")
        
        if mood in mood_instructions:
            mood_info = mood_instructions[mood]
            print(f"DEBUG: Found mood '{mood}' in instructions")
        else:
            # カスタム雰囲気の場合
            print(f"DEBUG: Custom mood '{mood}' - creating dynamic instructions")
            mood_info = {
                "tone": f"「{mood}」という雰囲気に合った独特な口調や表現で。この雰囲気を強く反映させた文体を使用してください。",
                "style": f"{mood}の雰囲気を表現する独自のスタイル",
                "example_words": [mood, "雰囲気", "表現", "スタイル"]
            }
        
        # 言語設定に基づく指示
        language_instruction = ""
        if language == "japanese_only":
            language_instruction = "日本語のみで投稿文を作成してください。"
        elif language == "english_only":
            language_instruction = "英語のみで投稿文を作成してください。"
        else:  # japanese_english
            language_instruction = "日本語の投稿文を作成し、その後に「---」で区切って英語翻訳も追加してください。"
        
        # 文字数指定を検出
        min_chars = 300  # デフォルト
        if "150文字以上" in mood or "150文字" in mood:
            min_chars = 150
        elif "200文字以上" in mood or "200文字" in mood:
            min_chars = 200
        
        base_prompt = f"""
以下の画像の内容に基づいて、指定された雰囲気に合わせてSNS投稿文を生成してください：

画像の内容: {image_description}

雰囲気設定: {mood}
文体指示: {mood_info['tone']}
表現スタイル: {mood_info['style']}
参考キーワード: {', '.join(mood_info['example_words'])}
最低文字数: {min_chars}文字以上

言語設定: {language_instruction}

重要: 
- 雰囲気「{mood}」の特徴を強く反映させ、他の雰囲気とは明確に区別できる文体で書いてください
- 最低{min_chars}文字以上の深く表現豊かな文章にしてください
- 指定された雰囲気を徹底的に表現してください
"""

        # Instagram用キャプション生成
        if language == "japanese_english":
            instagram_prompt = base_prompt + f"""
Instagram用のキャプションを日本語と英語で生成してください。「{mood}」の雰囲気を強く表現してください：

日本語キャプション:
[「{mood_info['style']}」で300文字以上の文章。{mood_info['tone']}]

ハッシュタグ（日本語）:
#タグ1 #タグ2 #タグ3...（雰囲気「{mood}」に関連するタグ10個程度）

---

English Caption:
[300+ character text in "{mood}" style with appropriate tone]

Hashtags (English):
#Tag1 #Tag2 #Tag3... (about 10 tags related to "{mood}" mood)

必須要件：
- 雰囲気「{mood}」の文体を徹底して使用
- 他の雰囲気と混同されない独特な表現
- {mood_info['tone']}を厳守
- 参考キーワードを活用: {', '.join(mood_info['example_words'])}
"""
        else:
            instagram_prompt = base_prompt + f"""
Instagram用のキャプションを以下の形式で生成してください。「{mood}」の雰囲気を強く表現：

キャプション:
[「{mood_info['style']}」で300文字以上の文章。{mood_info['tone']}]

ハッシュタグ:
#タグ1 #タグ2 #タグ3...（雰囲気「{mood}」に関連するタグ10個程度）

必須要件：
- 雰囲気「{mood}」の文体を徹底して使用
- 他の雰囲気と混同されない独特な表現
- {mood_info['tone']}を厳守
- 参考キーワードを活用: {', '.join(mood_info['example_words'])}
"""

        instagram_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": instagram_prompt}],
            max_tokens=600,
            temperature=0.8
        )
        
        # レスポンスを解析（新しい形式）
        instagram_content = instagram_response.choices[0].message.content.strip()
        
        if language == "japanese_english":
            # 日本語+英語の場合の解析
            parts = instagram_content.split('---')
            if len(parts) >= 2:
                japanese_part = parts[0].strip()
                english_part = parts[1].strip()
                
                # 日本語部分の解析
                jp_caption = ""
                jp_hashtags = []
                if "ハッシュタグ（日本語）:" in japanese_part:
                    jp_sections = japanese_part.split("ハッシュタグ（日本語）:")
                    jp_caption = jp_sections[0].replace("日本語キャプション:", "").strip()
                    jp_hashtags = jp_sections[1].strip().split()
                
                # 英語部分の解析
                en_caption = ""
                en_hashtags = []
                if "Hashtags (English):" in english_part:
                    en_sections = english_part.split("Hashtags (English):")
                    en_caption = en_sections[0].replace("English Caption:", "").strip()
                    en_hashtags = en_sections[1].strip().split()
                
                # 日本語と英語を結合
                combined_caption = jp_caption
                if en_caption:
                    combined_caption += "\n\n---\n\n" + en_caption
                
                combined_hashtags = jp_hashtags + en_hashtags
                
                instagram_data = {
                    "caption": combined_caption,
                    "hashtags": combined_hashtags[:10]  # 10個に制限
                }
            else:
                # フォールバック
                instagram_data = {
                    "caption": instagram_content,
                    "hashtags": ["#photo", "#beautiful", "#instagram"]
                }
        else:
            # 日本語のみ・英語のみの場合の解析
            if "ハッシュタグ:" in instagram_content:
                sections = instagram_content.split("ハッシュタグ:")
                caption = sections[0].replace("キャプション:", "").strip()
                hashtags = sections[1].strip().split()
            elif "Hashtags:" in instagram_content:
                sections = instagram_content.split("Hashtags:")
                caption = sections[0].replace("Caption:", "").strip()
                hashtags = sections[1].strip().split()
            else:
                # フォールバック
                caption = instagram_content
                hashtags = ["#photo", "#beautiful"]
            
            instagram_data = {
                "caption": caption,
                "hashtags": hashtags[:10]  # 10個に制限
            }

        # Twitter用スレッド生成
        caption_text = instagram_data.get('caption', '')
        hashtags = instagram_data.get('hashtags', [])[:5]  # 最初の5個のハッシュタグのみ
        
        twitter_prompt = f"""
以下の文章をX (Twitter)のスレッド形式に分割して、JSON配列で返してください：

{caption_text}

要件：
- 各ツイートは140文字以内に収める
- 自然な区切りで分割
- 最後のツイートにのみハッシュタグを追加: {' '.join(hashtags)}
- 2-4個のツイートに調整
- 必ずJSON配列形式で返す

例：["1/2 最初のツイート内容", "2/2 最後のツイート内容 #ハッシュタグ"]
"""

        twitter_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": twitter_prompt}],
            max_tokens=500,
            temperature=0.7
        )
        
        try:
            twitter_response_text = twitter_response.choices[0].message.content.strip()
            twitter_data = json.loads(twitter_response_text)
        except:
            # フォールバック: 自動分割
            caption = instagram_data.get('caption', '')
            hashtags_text = ' '.join(instagram_data.get('hashtags', [])[:5])
            
            # 文章を140文字以内に分割
            twitter_data = []
            remaining_text = caption
            tweet_num = 1
            
            while remaining_text:
                if len(remaining_text) <= 120:  # ハッシュタグ用に余裕を持たせる
                    twitter_data.append(f"{tweet_num}/{tweet_num} {remaining_text} {hashtags_text}")
                    break
                else:
                    # 自然な区切り点を探す
                    cut_point = 120
                    while cut_point > 80 and remaining_text[cut_point] not in '。！？\n ':
                        cut_point -= 1
                    
                    if cut_point <= 80:  # 適切な区切りが見つからない場合
                        cut_point = 120
                    
                    twitter_data.append(f"{tweet_num}/? {remaining_text[:cut_point]}")
                    remaining_text = remaining_text[cut_point:].strip()
                    tweet_num += 1
            
            # 最後のツイートにハッシュタグを追加
            if twitter_data and hashtags_text:
                last_index = len(twitter_data) - 1
                # 番号を修正
                for i, tweet in enumerate(twitter_data):
                    twitter_data[i] = tweet.replace(f"{i+1}/?", f"{i+1}/{len(twitter_data)}")
                    if i == last_index:
                        twitter_data[i] = f"{twitter_data[i]} {hashtags_text}"

        return {
            'instagram': instagram_data,
            'twitter': twitter_data,
            'threads': instagram_data.get('caption', '') + '\n\n' + ' '.join(instagram_data.get('hashtags', [])[:10])
        }
    
    def send_success_response(self, data):
        """成功レスポンス送信"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def send_error_response(self, error_data):
        """エラーレスポンス送信"""
        self.send_response(500)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(error_data, ensure_ascii=False).encode('utf-8'))
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response_data = {
            'success': True,
            'message': 'API is working',
            'method': 'GET'
        }
        
        self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()