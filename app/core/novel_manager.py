"""
小説データを管理するモジュール
"""
import threading
from app.utils.logger_manager import get_logger

# ロガーの設定
logger = get_logger('NovelManager')


class NovelManager:
    """小説データ管理クラス"""
    
    def __init__(self, db_manager):
        """
        初期化
        
        Args:
            db_manager: データベースマネージャのインスタンス
        """
        self.db_manager = db_manager
        self.novel_cache = {}  # {ncode: novel_data}
        self.episode_cache = {}  # {ncode: [episodes]}
        self.lock = threading.RLock()
        self.novels = []  # 全小説リスト
        self.last_read_novel = None
        self.last_read_episode = 0
    
    def load_novels(self):
        """小説データを読み込む"""
        with self.lock:
            try:
                # 全小説データを取得
                self.novels = self.db_manager.get_all_novels()
                logger.info(f"{len(self.novels)}件の小説データを読み込みました")
                
                # 最後に読んだ小説の情報を取得
                last_read_info = self.db_manager.get_last_read_novel()
                if last_read_info:
                    last_read_ncode, self.last_read_episode = last_read_info
                    
                    # 対応する小説情報を探す
                    for novel in self.novels:
                        if novel[0] == last_read_ncode:
                            self.last_read_novel = novel
                            break
                
                return True
            except Exception as e:
                logger.error(f"小説データの読み込みエラー: {e}")
                return False
    
    def get_all_novels(self):
        """
        全ての小説情報を取得
        
        Returns:
            list: 小説情報のリスト
        """
        with self.lock:
            return self.novels
    
    def get_novel(self, ncode):
        """
        指定されたncodeの小説情報を取得
        
        Args:
            ncode (str): 小説コード
            
        Returns:
            tuple: 小説情報
        """
        # キャッシュをチェック
        if ncode in self.novel_cache:
            return self.novel_cache[ncode]
        
        # データベースから取得
        novel = self.db_manager.get_novel_by_ncode(ncode)
        
        # キャッシュに保存
        if novel:
            self.novel_cache[ncode] = novel
        
        return novel
    
    def get_episodes(self, ncode):
        """
        指定された小説のエピソード一覧を取得
        
        Args:
            ncode (str): 小説コード
            
        Returns:
            list: エピソード情報のリスト
        """
        # キャッシュをチェック
        if ncode in self.episode_cache:
            return self.episode_cache[ncode]
        
        # データベースから取得
        episodes = self.db_manager.get_episodes_by_ncode(ncode)
        
        # キャッシュに保存
        if episodes:
            self.episode_cache[ncode] = episodes
            
        return episodes
    
    def update_last_read(self, ncode, episode_no):
        """
        最後に読んだ小説とエピソード番号を記録
        
        Args:
            ncode (str): 小説コード
            episode_no (int): エピソード番号
        """
        try:
            self.db_manager.update_last_read(ncode, episode_no)
            
            # 最後に読んだ小説情報を更新
            self.last_read_episode = episode_no
            
            if not self.last_read_novel or self.last_read_novel[0] != ncode:
                # 小説情報を更新
                self.last_read_novel = self.get_novel(ncode)
                
            logger.info(f"最後に読んだ小説を更新: {ncode}, エピソード: {episode_no}")
            
        except Exception as e:
            logger.error(f"最後に読んだ小説の更新エラー: {e}")
    
    def get_last_read_info(self):
        """
        最後に読んだ小説情報を取得
        
        Returns:
            tuple: (小説情報, エピソード番号)
        """
        return self.last_read_novel, self.last_read_episode
    
    def clear_cache(self, ncode=None):
        """
        キャッシュをクリア
        
        Args:
            ncode (str, optional): 特定の小説のキャッシュをクリアする場合は指定
        """
        with self.lock:
            if ncode:
                # 特定の小説のキャッシュをクリア
                if ncode in self.novel_cache:
                    del self.novel_cache[ncode]
                if ncode in self.episode_cache:
                    del self.episode_cache[ncode]
            else:
                # 全てのキャッシュをクリア
                self.novel_cache.clear()
                self.episode_cache.clear()
            
            logger.debug(f"キャッシュをクリアしました: {ncode if ncode else '全て'}")
    
    def reload_novels(self):
        """
        小説データを再読み込み
        """
        with self.lock:
            # キャッシュをクリア
            self.clear_cache()
            
            # 小説リストを更新
            self.novels = self.db_manager.get_all_novels()
            logger.info(f"{len(self.novels)}件の小説データを再読み込みしました")
