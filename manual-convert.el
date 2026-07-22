#!/usr/bin/env emacs --script

;; Manual conversion script for Квизи.org to new format

(defun quiz--manual-slugify (s)
  "Create a short slug from S."
  (let ((raw (downcase (string-trim s)))
        (one (replace-regexp-in-string "[[:space:]\n\r\t]+" " " raw))
        (slug (replace-regexp-in-string "[^[:alnum:]]+" "-" one)))
    (let ((trimmed (replace-regexp-in-string "^-+\\|-+$" "" slug)))
      (if (> (length trimmed) 40) (substring trimmed 0 40) trimmed))))

(defun quiz--make-id (question)
  "Create ID from QUESTION."
  (let ((sha (substring (md5 question) 0 8)))
    (concat (quiz--manual-slugify question) "-" sha)))

(defun quiz-convert-manually ()
  "Manually convert all questions to new format."
  (let ((input-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи.org")
        (output-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи-converted.org")
        (questions '())
        (current-category nil))
    
    (with-temp-buffer
      (insert-file-contents input-file)
      (goto-char (point-min))
      
      ;; Parse questions
      (while (re-search-forward "^\\(\\*+\\) \\(.*?\\)\\(?:\\s-+\\[\\([0-9]+\\)/[0-9]+\\]\\)?$" nil t)
        (let ((level (length (match-string 1)))
              (title (string-trim (match-string 2))))
          (cond 
           ;; Category header (***)
           ((= level 3)
            (setq current-category title))
           
           ;; Question (- [ ] text)
           ((and (= level 1) (string-prefix-p "- " title))
            (let ((question-text (string-trim (substring title 2)))
                  (answers '())
                  (correct-idx nil)
                  (start-pos (match-beginning 0))
                  (end-pos (line-end-position))
                  (next-pos (1+ end-pos)))
              
              ;; Extract answers (4 lines)
              (dotimes (i 4)
                (forward-line 1)
                (when (looking-at "^\\s-+-\\s-\\[\\(.\\)\\]\\s-\\(.*\\)$")
                  (let ((checkbox (match-string 1))
                        (answer-text (string-trim (match-string 2))))
                    (push answer-text answers)
                    (when (string= checkbox "X")
                      (setq correct-idx i)))))
              
              (setq answers (nreverse answers))
              (when (and answers current-category correct-idx)
                (push (list :category current-category
                            :question question-text
                            :answers answers
                            :correct correct-idx
                            :start start-pos
                            :end (point))
                      questions)))))))
      
      ;; Generate converted output
      (with-temp-file output-file
        (insert ":PROPERTIES:\n")
        (insert ":ID:       26ad5ae6-8e94-4de3-a0b6-88e02266d639\n")
        (insert ":END:\n")
        (insert "#+title: Квизи (Converted)\n\n")
        (insert "* Вопросы\n")
        (insert ":PROPERTIES:\n")
        (insert ":ID:       fb8e6949-be87-49a9-b252-c98f4a3deb35\n")
        (insert ":END:\n")
        (insert "** Категории\n\n")
        
        ;; Convert all questions
        (dolist (q (nreverse questions))
          (let ((category (plist-get q :category))
                (question-text (plist-get q :question))
                (answers (plist-get q :answers))
                (correct (plist-get q :correct))
                (question-id (quiz--make-id question-text)))
            
            (insert (format "*** %s\n" category))
            (insert (format "**** %s\n" question-text))
            (insert ":PROPERTIES:\n")
            (insert (format ":ID: %s\n" question-id))
            (insert (format ":CORRECT: %d\n" (1+ correct)))
            (dotimes (i 4)
              (insert (format ":ANSWER%d: %s\n" (1+ i) (nth i answers))))
            (insert ":END:\n\n")))))
    
    (message "Conversion completed. Output saved to: %s" output-file)
    (message "Total questions converted: %d" (length questions))))

;; Run conversion
(quiz-convert-manually)