#!/usr/bin/env emacs --script

;; Complete conversion script for all quiz questions

(defun quiz--generate-id-from-text (text)
  "Generate ID from TEXT."
  (let ((slug (downcase (replace-regexp-in-string "[^a-zа-я0-9]+" "-" text))))
    (concat (substring slug 0 (min 40 (length slug))) "-" (format "%04x" (sxhash text)))))

(defun quiz-convert-complete ()
  "Convert complete quiz file with all questions."
  (let ((input-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи.org")
        (output-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи-converted.org")
        questions '())
    
    (with-temp-buffer
      (insert-file-contents input-file)
      (goto-char (point-min))
      
      ;; Parse all questions
      (let ((current-category nil)
            (in-category-section nil))
        
        (while (re-search-forward "^\\(\\*+\\) \\(.*\\)$" nil t)
          (let ((level (length (match-string 1)))
                (title (string-trim (match-string 2))))
            
            (cond
             ;; Category header (*** Category)
             ((= level 3)
              (setq current-category title)
              (setq in-category-section t))
             
             ;; Question line (starting with -)
             ((and (= level 1) (string-prefix-p "- " title) in-category-section current-category)
              (let ((question-text (string-trim (substring title 2)))
                    (answers '())
                    (correct-answer nil)
                    (start-pos (point)))
                
                ;; Get 4 answer lines
                (dotimes (i 4)
                  (forward-line 1)
                  (when (re-search-forward "^\\s-+-\\s-\\[\\([X ]\\)\\]\\s-\\(.*\\)$" (line-end-position) t)
                    (let ((checkbox (match-string 1))
                          (answer-text (string-trim (match-string 2))))
                      (push answer-text answers)
                      (when (string= checkbox "X")
                        (setq correct-answer (1+ i))))))
                
                (setq answers (nreverse answers))
                (when (and answers correct-answer)
                  (push (list :category current-category
                              :question question-text
                              :answers answers
                              :correct correct-answer)
                        questions)))))))
      
      ;; Generate output
      (with-temp-file output-file
        (insert ":PROPERTIES:\n")
        (insert ":ID:       quiz-converted\n")
        (insert ":END:\n")
        (insert "#+title: Квизи - Converted\n\n")
        (insert "* Вопросы\n")
        (insert ":PROPERTIES:\n")
        (insert ":ID:       quiz-questions\n")
        (insert ":END:\n")
        (insert "** Категории\n\n")
        
        ;; Output all questions grouped by category
        (let ((categories '()))
          ;; Group questions by category
          (dolist (q questions)
            (let ((cat (plist-get q :category)))
              (unless (assoc cat categories)
                (push (list cat) categories))
              (setcdr (assoc cat categories)
                      (cons q (cdr (assoc cat categories))))))
          
          ;; Output each category
          (dolist (cat-item categories)
            (let ((cat-name (car cat-item))
                  (cat-questions (cdr cat-item)))
              (insert (format "*** %s\n\n" cat-name))
              (dolist (q cat-questions)
                (insert (format "**** %s\n" (plist-get q :question)))
                (insert ":PROPERTIES:\n")
                (insert (format ":ID:       %s\n" (quiz--generate-id-from-text (plist-get q :question))))
                (insert (format ":CORRECT:   %d\n" (plist-get q :correct)))
                (let ((answers (plist-get q :answers)))
                  (dotimes (i 4)
                    (insert (format ":ANSWER%d:   %s\n" (1+ i) (or (nth i answers) ""))))
                (insert ":END:\n\n"))))))
      
      (message "Conversion completed successfully!")
      (message "Total questions converted: %d" (length questions)))))

;; Run the conversion
(quiz-convert-complete)